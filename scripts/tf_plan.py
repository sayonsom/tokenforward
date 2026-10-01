"""TokenForward planner: deterministic, runs locally, costs zero LLM tokens.

Reads a spec (a Spec Kit spec.md / tasks.md, any markdown ticket, or only the lines changed since a git ref),
locates the code each item touches (graphify graph if present, else git grep), sizes the reads from real
line counts, and simulates the agent loop turn by turn:

    etok per turn = 0.1 * context_so_far + 1.25 * new_input + 5 * output

Context grows across items in one session, so later items cost more than earlier ones. Items are admitted
in spec order while the cumulative estimate stays under 90% of the budget (10% reserve). The estimate is
multiplied by a per-repo calibration factor learned from past receipts (actual / estimated).
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess

TOK_PER_LINE = 11          # typical Python source, incl. line-number prefixes from the Read tool
BASE_CONTEXT = 24_000      # system prompt + tools + CLAUDE.md, first turn
READ_WINDOW_MAX = 150      # lines per ranged read
FILE_HEADER_LINES = 40     # imports / __all__ / neighbours read around an edit
TEST_READ_LINES = 80       # existing tests read to copy conventions
TEST_OUTPUT_TOKENS = 1_500 # one targeted pytest run
STOP = set("""the and for with that this from into when then than each only must should will also
where which what true false none none self args kwargs return returns value values type types
test tests add adds added new make update support supports existing default optional same see
python class def import file files docs doc code versionadded versionchanged note""".split())
AMBIGUOUS = 2              # a name defined in more places than this is too generic to locate


# ---------------- spec parsing ----------------

ITEM_PATTERNS = [
    re.compile(r"^\s*- \[[ xX]\]\s+(T\d+.*)$"),                  # Spec Kit tasks.md
    re.compile(r"^\s*[-*]?\s*\**((?:FR|NFR|SC)-\d+\**:?.*)$"),    # Spec Kit spec.md requirements
    re.compile(r"^\s*(\d+[.)]\s+.+)$"),                          # numbered list
    re.compile(r"^\s*[-*]\s+(.+)$"),                              # bullets
]


def changed_lines(path: str, since: str, cwd: str) -> list[str]:
    out = subprocess.run(["git", "diff", "-U0", since, "--", path], cwd=cwd, capture_output=True,
                         text=True, encoding="utf-8", errors="replace").stdout
    return [l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]


def parse_items(text_lines: list[str]) -> list[str]:
    for pat in ITEM_PATTERNS:
        items, cur = [], None
        for line in text_lines:
            m = pat.match(line)
            if m:
                cur = m.group(1).strip()
                items.append(cur)
            elif cur is not None and line.startswith(("   ", "\t")) and line.strip():
                items[-1] += " " + line.strip()      # continuation lines
            else:
                cur = None
        if len(items) >= 2:
            return items
    paras = [p.strip() for p in "\n".join(text_lines).split("\n\n") if p.strip()]
    return paras or ["\n".join(text_lines)]


def keywords(item: str) -> list[str]:
    ticks = [t for t in re.findall(r"`([^`]+)`", item) if "/" not in t]  # paths handled separately
    ks: list[str] = []
    for t in ticks:
        t = re.sub(r"\(.*", "", t)          # `f(a, b=1)` -> `f`: argument names are not code locations
        for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", t):
            if len(ident) >= 3 and ident.lower() not in STOP and ident not in ("np", "numpy") \
                    and not ident.startswith("__"):
                ks.append(ident)
    rest = re.sub(r"`[^`]+`", " ", item)
    ks += re.findall(r"\b[a-z]+_[a-z0-9_]+\b|\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b", rest)
    seen, out = set(), []
    for k in ks:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out[:8]


# ---------------- code location ----------------

class Locator:
    def __init__(self, root: str):
        self.root = root
        self.by_name: dict[str, list[tuple[str, int]]] = {}
        self.file_lines: dict[str, list[int]] = {}
        gp = os.path.join(root, "graphify-out", "graph.json")
        self.source = "graphify" if os.path.exists(gp) else "git grep"
        if self.source == "graphify":
            g = json.load(open(gp, encoding="utf-8"))
            for n in g.get("nodes", []):
                f, loc = n.get("source_file"), n.get("source_location") or ""
                if not f or not loc.startswith("L"):
                    continue
                try:
                    line = int(loc[1:].split("-")[0])
                except ValueError:
                    continue
                name = (n.get("label") or "").rstrip("()").split(".")[-1]
                self.by_name.setdefault(name, []).append((f, line))
                self.file_lines.setdefault(f, []).append(line)
            for f in self.file_lines:
                self.file_lines[f].sort()

    def _grep(self, name: str) -> list[tuple[str, int]]:
        r = subprocess.run(["git", "grep", "-n", "-E", rf"^\s*(async\s+)?(def|class)\s+{re.escape(name)}\b"],
                           cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        hits = []
        for l in r.stdout.splitlines()[:6]:
            f, ln, _ = l.split(":", 2)
            hits.append((f, int(ln)))
        return hits

    def span(self, f: str, line: int) -> int:
        """Lines from this symbol to the next symbol in the same file (graph) or a fixed guess (grep)."""
        lines = self.file_lines.get(f)
        if lines:
            nxt = [x for x in lines if x > line]
            return max(10, min((nxt[0] - line) if nxt else 60, 400))
        return 60

    def find(self, name: str) -> list[tuple[str, int]]:
        hits = self.by_name.get(name, []) if self.source == "graphify" else self._grep(name)
        src_hits = [h for h in hits if "test" not in h[0]]
        if len(src_hits) > AMBIGUOUS:
            return []
        # prefer source over tests/vendored, keep it small
        hits = sorted(hits, key=lambda h: ("test" in h[0], "/_vendor" in h[0] or "/vendor" in h[0], h[0]))
        return hits[:3]


# ---------------- cost simulation ----------------

class Sim:
    def __init__(self, base_ctx: int):
        self.ctx = base_ctx
        self.etok = 1.25 * base_ctx  # first turn writes the base context to cache
        self.turns = 0

    def turn(self, new_in: int = 0, out: int = 150):
        self.etok += 0.1 * self.ctx + 1.25 * new_in + 5 * out
        self.ctx += new_in + out
        self.turns += 1


def item_work(item: str, loc: Locator) -> dict:
    """Regions = (file, first line, lines to read). Paths named in the spec are touched directly."""
    regions, symbols = [], []
    for k in keywords(item):
        for f, line in loc.find(k):
            symbols.append(f"{k}@{f}:{line}")
            regions.append((f, line, min(loc.span(f, line), READ_WINDOW_MAX)))
    for t in re.findall(r"`([^`]+)`", item):
        path = t.strip().split("<")[0].rstrip("/")
        if "/" in path:
            full = os.path.join(loc.root, path)
            if os.path.isfile(full):   # e.g. a stub file: read the relevant windows, not the whole file
                regions.append((path, 1, min(sum(1 for _ in open(full, "rb")), 3 * READ_WINDOW_MAX)))
            else:                      # new file to create (release note, docs page)
                regions.append((path, 0, 0))
    files = sorted({r[0] for r in regions})
    return {"item": item, "symbols": symbols[:6], "files": files, "regions": regions}


def simulate(works: list[dict], base_ctx: int, calib: float, budget: int) -> dict:
    sim = Sim(base_ctx)
    sim.turn(out=400)                       # spec card
    rows, admitted = [], []
    limit = 0.9 * budget
    seen: set[tuple[str, int]] = set()      # regions already in context are not re-read
    seen_files: set[str] = set()
    for w in works:
        before = sim.etok
        new = [r for r in w["regions"] if (r[0], r[1]) not in seen]
        new_lines = sum(r[2] for r in new) + sum(FILE_HEADER_LINES for f in {r[0] for r in new if r[2]} - seen_files)
        if any("test" not in r[0] for r in new) and not any("test" in f for f in seen_files):
            new_lines += TEST_READ_LINES
        seen |= {(r[0], r[1]) for r in new}
        seen_files |= {r[0] for r in new}
        src_lines = sum(r[2] for r in w["regions"] if "test" not in r[0])
        w["read_lines"] = new_lines
        w["changed_lines"] = changed = 12 + int(0.12 * src_lines) + 20 if w["regions"] else 25
        reads = math.ceil(len({r[0] for r in new}) / 3)     # parallel ranged reads, 3 per turn
        for _ in range(reads):
            sim.turn(new_in=new_lines * TOK_PER_LINE // reads)
        edits = max(1, len(w["files"]))
        for _ in range(edits):
            sim.turn(new_in=200, out=changed * 12 // edits + 80)
        sim.turn(new_in=TEST_OUTPUT_TOKENS)                 # targeted test run
        marginal = (sim.etok - before) * calib
        total = sim.etok * calib
        fits = total + (0.1 * sim.ctx + 5 * 300) * calib <= limit   # + final changelog turn
        rows.append({**{k: v for k, v in w.items() if k != "regions"}, "marginal_etok": int(marginal), "cumulative_etok": int(total), "fits": fits})
        if fits and len(admitted) == len(rows) - 1:          # admit in order; stop at first miss
            admitted.append(len(rows) - 1)
    sim.turn(new_in=2_000)                  # one broad test run
    sim.turn(out=300)                       # changelog
    return {"rows": rows, "admitted": admitted, "all_items_etok": int(sim.etok * calib), "turns": sim.turns}


# ---------------- calibration ----------------

def calib_path(root):
    return os.path.join(root, ".tokenforward", "calibration.json")


def load_calibration(root) -> tuple[float, int]:
    try:
        ratios = json.load(open(calib_path(root), encoding="utf-8"))["ratios"][-5:]
    except (OSError, ValueError, KeyError):
        return 1.0, 0
    ratios = sorted(ratios)
    return (ratios[len(ratios) // 2] if ratios else 1.0), len(ratios)


def record_calibration(root, estimate: float, actual: float):
    if estimate <= 0 or actual <= 0:
        return
    p = calib_path(root)
    try:
        d = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        d = {"ratios": []}
    prev, _ = load_calibration(root)
    d["ratios"].append(round(max(0.3, min(3.0, prev * actual / estimate)), 3))
    d["ratios"] = d["ratios"][-10:]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)


# ---------------- entry point ----------------

def plan(root: str, budget: int, spec: str | None, since: str | None, base_ctx: int = BASE_CONTEXT) -> dict:
    if spec and os.path.exists(os.path.join(root, spec)):
        lines = changed_lines(spec, since, root) if since else \
            open(os.path.join(root, spec), encoding="utf-8").read().splitlines()
        spec_name = spec
    else:
        lines, spec_name = (spec or "").splitlines(), "inline"
    items = parse_items(lines)
    loc = Locator(root)
    calib, n_calib = load_calibration(root)
    works = [item_work(it, loc) for it in items]
    res = simulate(works, base_ctx, calib, budget)
    res.update(budget=budget, spec=spec_name, since=since, locator=loc.source,
               calibration=calib, calibration_runs=n_calib,
               estimate_admitted=res["rows"][res["admitted"][-1]]["cumulative_etok"] if res["admitted"] else 0)
    return res


def render(res: dict) -> str:
    fmt = lambda n: f"{n / 1000:.1f}k"  # noqa: E731
    head = (f"TokenForward plan: {res['spec']}{' (changed since ' + res['since'] + ')' if res['since'] else ''} | "
            f"budget {fmt(res['budget'])} etok | locator: {res['locator']} | "
            f"calibration x{res['calibration']:.2f} from {res['calibration_runs']} run(s)")
    out = [head, "", "| # | Fits | Item | Marginal | Cumulative | Touches |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(res["rows"]):
        mark = "yes" if i in res["admitted"] else "DEFER"
        item = (r["item"][:70] + "...") if len(r["item"]) > 73 else r["item"]
        touches = ", ".join(os.path.basename(f) for f in r["files"][:3]) or "-"
        out.append(f"| {i + 1} | {mark} | {item.replace('|', '/')} | {fmt(r['marginal_etok'])} | "
                   f"{fmt(r['cumulative_etok'])} | {touches} |")
    n, tot = len(res["admitted"]), len(res["rows"])
    out += ["", f"Fits: {n}/{tot} items, est {fmt(res['estimate_admitted'])} of {fmt(res['budget'])} (10% reserve kept). "
                f"All items would need ~{fmt(res['all_items_etok'])}."]
    if res["calibration_runs"] == 0:
        out.append("Uncalibrated: first run in this repo; expect +-40%. Each receipt tightens it.")
    return "\n".join(out)
