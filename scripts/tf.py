#!/usr/bin/env python3
"""TokenForward: budget-first agentic development for Claude Code.

One stdlib-only file. Subcommands:
  hook-prompt | hook-pretool | hook-posttool | hook-stop   (Claude Code hooks, JSON on stdin)
  statusline                                              (Claude Code statusLine command)
  status | off                                            (manual control, run inside the project)

Budget unit: "effective tokens" (etok) = input-token equivalents, priced like the API:
  etok = input + 1.25*cache_write + 0.1*cache_read + 5*output
For every current Claude model output costs 5x input, so etok is proportional to dollars:
  usd = etok * TF_USD_PER_MTOK_IN / 1e6   (default 3.0; set it to your model's input price)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time

W_IN, W_CW, W_CR, W_OUT = 1.0, 1.25, 0.1, 5.0
USD_PER_MTOK = float(os.environ.get("TF_USD_PER_MTOK_IN", "3.0"))
BIG_FILE_LINES = int(os.environ.get("TF_BIG_FILE_LINES", "300"))
ENFORCE = os.environ.get("TF_ENFORCE", "1") != "0"

# Forward allocation: the budget is committed to phases before work starts.
PHASES = [("map", 0.25), ("build", 0.45), ("verify", 0.20), ("reserve", 0.10)]

PROTOCOL = """TokenForward budget active: {budget} etok (~${usd:.2f}). Phases: map 25% | build 45% | verify 20% | reserve 10%.
Rules:
1. Map: {map_hint} Grep -n to locate, then Read with offset/limit (<=120 lines). Never read a whole file over {big} lines. Never re-read a range already in context.
2. Spec card, in your reply, <=8 lines: Goal / Interface / Touch (files) / Acceptance (test names) / Out of scope. No spec files, no plan files. Ambiguity: state one assumption, continue.
3. Write the failing tests first. They are the spec. Then the smallest implementation that passes.{ponytail}
4. Verify: targeted `pytest <file> -q -x` first, then one broad `pytest -q` run. Fix, do not rewrite.
5. Batch independent tool calls in one turn. No narration between tool calls. Prefer Edit over Write.
6. At 80% spend: finish mode, no new exploration. At 100% tools are blocked: stop and report.
7. Final reply is the changelog, nothing else, <=8 lines:
   Done: <items> | Deferred: <items + reason> | Files: <paths> | Tests: <pass/total, command> | Notes: <one line, only if needed>{plan}"""

PLAN_CTX = """
Plan (computed locally, 0 tokens): implement ONLY these items, in order: {admitted}. Deferred by budget: {deferred}.
Estimate {est} of {budget}. Do not start a deferred item; list it under Deferred."""


def eprint(*a):
    print(*a, file=sys.stderr)


def parse_budget(text: str) -> int | None:
    t = text.lower().replace(",", "")
    pats = [
        r"^\s*/(?:tokenforward:)?tfd\s+(\d+(?:\.\d+)?)\s*([km]?)\b",
        r"(?:budget|max(?:imum)?|spend|cap|limit)[^\d\n]{0,25}(\d+(?:\.\d+)?)\s*([km]?)\s*(?:e?tok(?:en)?s?)\b",
        r"(\d+(?:\.\d+)?)\s*([km]?)\s*(?:e?tok(?:en)?s?)\s*(?:budget|max|cap|limit)\b",
    ]
    for p in pats:
        m = re.search(p, t)
        if m:
            n = float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2)]
            return int(n) if n >= 1000 else None
    return None


# ---------- state ----------

def state_path(cwd: str) -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
    d = os.path.join(root, ".tokenforward")
    os.makedirs(d, exist_ok=True)
    gi = os.path.join(d, ".gitignore")
    if not os.path.exists(gi):
        open(gi, "w", encoding="utf-8").write("*\n")
    return os.path.join(d, "state.json")


def load(cwd):
    try:
        return json.load(open(state_path(cwd), encoding="utf-8"))
    except Exception:
        return {}


def save(cwd, st):
    p = state_path(cwd)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    os.replace(tmp, p)


# ---------- usage accounting ----------

def transcript_files(tp: str) -> list[str]:
    if not tp:
        return []
    files = [tp] if os.path.exists(tp) else []
    base = tp[:-6] if tp.endswith(".jsonl") else tp
    files += glob.glob(os.path.join(base, "subagents", "*.jsonl"))  # subagent sidechains
    return files


def usage(tp: str) -> dict:
    """Sum usage across main + subagent transcripts, deduped by message id."""
    seen: dict[str, dict] = {}
    turns = 0
    for f in transcript_files(tp):
        try:
            fh = open(f, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                msg = o.get("message") or {}
                u = msg.get("usage")
                if o.get("type") != "assistant" or not u:
                    continue
                mid = msg.get("id") or o.get("uuid") or str(len(seen))
                seen[f + mid] = u
    tot = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    for u in seen.values():
        turns += 1
        tot["input"] += u.get("input_tokens", 0) or 0
        tot["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
        tot["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        tot["output"] += u.get("output_tokens", 0) or 0
    tot["etok"] = int(tot["input"] * W_IN + tot["cache_write"] * W_CW
                      + tot["cache_read"] * W_CR + tot["output"] * W_OUT)
    tot["turns"] = turns
    return tot


def spent(sess: dict, tp: str) -> tuple[int, dict]:
    u = usage(tp)
    return max(0, u["etok"] - sess.get("base_etok", 0)), u


def fmt(n: int) -> str:
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.1f}k"


def phase_limits(budget: int) -> dict:
    out, acc = {}, 0.0
    for name, frac in PHASES:
        acc += frac
        out[name] = int(budget * acc)
    return out


# ---------- ecosystem detection ----------

def has_graph(cwd: str) -> bool:
    return os.path.exists(os.path.join(cwd or ".", "graphify-out", "graph.json"))


def has_ponytail() -> bool:
    if os.environ.get("TF_PONYTAIL") == "1":
        return True
    home = os.path.expanduser("~/.claude/plugins")
    return bool(glob.glob(os.path.join(home, "**", "ponytail*"), recursive=True)) or \
        "ponytail" in os.environ.get("TF_PLUGIN_DIRS", "")


# ---------- hooks ----------

def out(obj):
    print(json.dumps(obj))
    sys.exit(0)


def activate(st: dict, sid: str, cwd: str, tp: str, budget: int, plan: dict | None = None) -> str:
    """Start (or restart) a budgeted session and return the protocol text to inject."""
    u = usage(tp)
    st[sid] = {"budget": budget, "base_etok": u["etok"], "phase": "map", "reads": {},
               "denied_big": [], "warned80": False, "started": time.time(), "phase_at": {},
               "ecosystem": {"graphify": has_graph(cwd), "ponytail": has_ponytail()},
               "plan_estimate": (plan or {}).get("estimate_admitted", 0),
               "plan_items": (plan or {}).get("items", {})}
    save(cwd, st)
    eco = st[sid]["ecosystem"]
    plan_txt = ""
    if plan:
        it = plan["items"]
        plan_txt = PLAN_CTX.format(admitted=", ".join(it["admitted"]) or "none",
                                   deferred=", ".join(it["deferred"]) or "none",
                                   est=fmt(plan["estimate_admitted"]), budget=fmt(budget))
    return PROTOCOL.format(
        budget=fmt(budget), usd=budget * USD_PER_MTOK / 1e6, big=BIG_FILE_LINES, plan=plan_txt,
        map_hint=("`graphify query \"<question>\"` first (graph is built)." if eco["graphify"]
                  else "No graph: use Glob on names only."),
        ponytail=(" Ponytail rules apply: stdlib first, no speculative code." if eco["ponytail"] else
                  " Minimal code: stdlib first, no speculative options, no docstrings beyond one line."))


def hook_prompt(ev: dict):
    cwd, sid, tp = ev.get("cwd", ""), ev.get("session_id", "x"), ev.get("transcript_path", "")
    st = load(cwd)
    b = parse_budget(ev.get("prompt", ""))
    if b:
        out({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                    "additionalContext": activate(st, sid, cwd, tp, b)}})
    sess = st.get(sid)
    if sess:
        s, _ = spent(sess, tp)
        out({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
             "additionalContext": f"TokenForward: {fmt(s)}/{fmt(sess['budget'])} etok used, phase {sess['phase']}."}})
    sys.exit(0)


def deny(reason: str):
    out({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                "permissionDecision": "deny", "permissionDecisionReason": reason}})


def line_count(path: str) -> int:
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def hook_pretool(ev: dict):
    cwd, sid, tp = ev.get("cwd", ""), ev.get("session_id", "x"), ev.get("transcript_path", "")
    st = load(cwd)
    sess = st.get(sid)
    if not sess or not ENFORCE:
        sys.exit(0)
    s, _ = spent(sess, tp)
    tool, ti = ev.get("tool_name", ""), ev.get("tool_input", {}) or {}
    if s >= sess["budget"]:
        deny(f"TokenForward: budget exhausted ({fmt(s)}/{fmt(sess['budget'])}). "
             "Do not call more tools. Reply with: what is done, what is left, exact next command.")

    if tool == "Read":
        fp = ti.get("file_path", "")
        off, lim = ti.get("offset"), ti.get("limit")
        key = f"{fp}:{off or 0}:{lim or 'all'}"
        n = line_count(fp)
        if lim is None and n > BIG_FILE_LINES and fp not in sess["denied_big"]:
            sess["denied_big"].append(fp)
            save(cwd, st)
            deny(f"TokenForward: {os.path.basename(fp)} has {n} lines (~{n * 12 // 1000}k tokens, "
                 f"paid again on every later turn). Locate with Grep -n "
                 f"{'or graphify query ' if sess['ecosystem'].get('graphify') else ''}"
                 f"then Read with offset/limit <= 120. Retry once more to override.")
        if key in sess["reads"] and key not in sess.setdefault("denied_rr", []):
            sess["denied_rr"].append(key)
            save(cwd, st)
            deny(f"TokenForward: {os.path.basename(fp)} range already read at turn "
                 f"{sess['reads'][key]} and unchanged since. Use what is in context (retry to override after compaction).")
        sess["reads"][key] = usage(tp)["turns"]
        save(cwd, st)

    if tool == "Bash":
        cmd = ti.get("command", "")
        m = re.match(r"\s*cat\s+([^\s|;&>]+)\s*$", cmd)
        if m and line_count(os.path.join(cwd, m.group(1))) > BIG_FILE_LINES:
            deny("TokenForward: cat of a large file. Use Grep -n, then Read with offset/limit.")
    sys.exit(0)


def hook_posttool(ev: dict):
    cwd, sid, tp = ev.get("cwd", ""), ev.get("session_id", "x"), ev.get("transcript_path", "")
    st = load(cwd)
    tool, ti = ev.get("tool_name", ""), ev.get("tool_input", {}) or {}
    pend = os.path.join(os.path.dirname(state_path(cwd)), "pending.json")
    if tool == "Bash" and re.search(r"tf(-launch\.js|\.py)\S*\s+plan\b", ti.get("command", "")) \
            and os.path.exists(pend):
        plan = json.load(open(pend, encoding="utf-8"))
        os.remove(pend)
        out({"hookSpecificOutput": {"hookEventName": "PostToolUse",
             "additionalContext": activate(st, sid, cwd, tp, plan["budget"], plan)}})
    sess = st.get(sid)
    if not sess:
        sys.exit(0)
    s, _ = spent(sess, tp)
    # Zero-cost phase inference: first edit -> build, first test run after an edit -> verify.
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        fp = ti.get("file_path", "")
        sess["reads"] = {k: v for k, v in sess["reads"].items() if not k.startswith(fp + ":")}
        if sess["phase"] == "map":
            sess["phase"], sess["phase_at"]["build"] = "build", s
    if tool == "Bash" and re.search(r"\b(pytest|tox|nox|unittest|run_tests)\b", ti.get("command", "")) \
            and sess["phase"] == "build":
        sess["phase"], sess["phase_at"]["verify"] = "verify", s
    msgs = []
    lim = phase_limits(sess["budget"])
    if sess["phase"] == "map" and s > lim["map"] and not sess.get("warned_map"):
        sess["warned_map"] = True
        msgs.append(f"TokenForward: map phase over allocation ({fmt(s)} > {fmt(lim['map'])}). "
                    "Stop exploring. Write the spec card and the failing tests now.")
    if s >= 0.8 * sess["budget"] and not sess["warned80"]:
        sess["warned80"] = True
        msgs.append(f"TokenForward: 80% spent ({fmt(s)}/{fmt(sess['budget'])}). Finish mode: "
                    "no new reads, close out the current change, run the tests once.")
    save(cwd, st)
    if msgs:
        out({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": " ".join(msgs)}})
    sys.exit(0)


def hook_stop(ev: dict):
    cwd, sid, tp = ev.get("cwd", ""), ev.get("session_id", "x"), ev.get("transcript_path", "")
    st = load(cwd)
    sess = st.get(sid)
    if not sess:
        sys.exit(0)
    s, u = spent(sess, tp)
    rec = {"session_id": sid, "budget": sess["budget"], "spent_etok": s,
           "pct": round(100 * s / sess["budget"], 1), "usd_est": round(s * USD_PER_MTOK / 1e6, 4),
           "phase_final": sess["phase"], "phase_at": sess["phase_at"], "usage_raw": u,
           "ecosystem": sess["ecosystem"], "denied_big_reads": sess["denied_big"],
           "elapsed_s": round(time.time() - sess["started"], 1)}
    d = os.path.join(os.path.dirname(state_path(cwd)), "receipts")
    os.makedirs(d, exist_ok=True)
    rec["plan_estimate"] = sess.get("plan_estimate", 0)
    with open(os.path.join(d, f"{sid}.json"), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    root = os.path.dirname(os.path.dirname(state_path(cwd)))
    if sess.get("plan_estimate") and not sess.get("calibrated"):
        import tf_plan
        tf_plan.record_calibration(root, sess["plan_estimate"], s)
        sess["calibrated"] = True
        save(cwd, st)
    write_changelog(root, sess, s, last_assistant_text(tp))
    sys.exit(0)


def last_assistant_text(tp: str) -> str:
    text = ""
    try:
        with open(tp, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if '"assistant"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("type") != "assistant":
                    continue
                parts = [c.get("text", "") for c in (o.get("message") or {}).get("content") or []
                         if isinstance(c, dict) and c.get("type") == "text"]
                if any(p.strip() for p in parts):
                    text = "\n".join(parts).strip()
    except OSError:
        pass
    return text


def write_changelog(root: str, sess: dict, spent_etok: int, reply: str):
    """Append one minimal entry per finished turn: the agent's changelog reply + measured numbers."""
    import subprocess
    try:
        stat = subprocess.run(["git", "diff", "--stat", "HEAD"], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=10).stdout.strip().splitlines()
        stat = stat[-1].strip() if stat else "no changes"
    except (OSError, subprocess.SubprocessError):
        stat = "git unavailable"
    est = sess.get("plan_estimate") or 0
    lines = [f"## {time.strftime('%Y-%m-%d %H:%M')}",
             reply[:1500] or "(no reply text)",
             f"Spend: {fmt(spent_etok)}/{fmt(sess['budget'])} etok (~${spent_etok * USD_PER_MTOK / 1e6:.2f})"
             + (f", planned {fmt(est)}" if est else "") + f" | Diff: {stat}", ""]
    with open(os.path.join(root, ".tokenforward", "CHANGELOG.md"), "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def cmd_plan(argv: list[str]):
    """tf plan <budget> [<spec.md> | -] [--since <git ref>]   (spec from a file, stdin '-', or changed lines)"""
    import argparse
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import tf_plan
    ap = argparse.ArgumentParser(prog="tf plan")
    ap.add_argument("budget")
    ap.add_argument("spec", nargs="?", default=None)
    ap.add_argument("--since", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry", action="store_true", help="plan only; do not arm the budget for the session")
    a = ap.parse_args(argv)
    budget = parse_budget(f"/tfd {a.budget}") or int(float(a.budget))
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    spec = sys.stdin.read() if a.spec == "-" else a.spec
    res = tf_plan.plan(root, budget, spec, a.since)
    rows = res["rows"]
    label = lambda i: (re.match(r"\**((?:FR|NFR|SC)-\d+|T\d+|\d+)", rows[i]["item"]) or  # noqa: E731
                       re.match(r"(.{0,40})", rows[i]["item"])).group(1).strip("*. )")
    res["items"] = {"admitted": [label(i) for i in res["admitted"]],
                    "deferred": [label(i) for i in range(len(rows)) if i not in res["admitted"]]}
    d = os.path.dirname(state_path(root))
    files = [("plan.json", json.dumps(res, indent=1)), ("plan.md", tf_plan.render(res))]
    if not a.dry:
        files.append(("pending.json", json.dumps({k: res[k] for k in ("budget", "estimate_admitted", "items")})))
    for name, body in files:
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(body)
    print(json.dumps(res, indent=1) if a.json else tf_plan.render(res))


def cmd_sessions(argv: list[str]):
    """tf sessions [dir ...]  Token totals of recent Claude Code sessions run in these folders (default: cwd)."""
    dirs = [os.path.normcase(os.path.abspath(d)) for d in (argv or [os.getcwd()])]
    root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    rows = []
    for f in glob.glob(os.path.join(root, "*", "*.jsonl")):
        if time.time() - os.path.getmtime(f) > 3 * 86400:
            continue
        cwd = ""
        with open(f, encoding="utf-8", errors="ignore") as fh:
            for i, line in enumerate(fh):
                m = re.search(r'"cwd":\s*"((?:[^"\\]|\\.)*)"', line)
                if m:
                    cwd = json.loads('"' + m.group(1) + '"')
                    break
                if i > 50:
                    break
        if not cwd:
            continue
        nc = os.path.normcase(os.path.abspath(cwd))
        if not any(nc == d or nc.startswith(d + os.sep) for d in dirs):
            continue
        u = usage(f)
        if u["turns"]:
            rows.append((os.path.getmtime(f), os.path.basename(f)[:8], cwd, u))
    rows.sort()
    if not rows:
        print("No sessions found for", ", ".join(dirs))
        return
    print(f"{'when':<6} {'session':<9} {'folder':<28} {'turns':>5} {'eff. tokens':>12} {'raw tokens':>12} {'~USD':>7}")
    for t, sid, cwd, u in rows:
        raw = u["input"] + u["cache_write"] + u["cache_read"] + u["output"]
        print(f"{time.strftime('%H:%M', time.localtime(t)):<6} {sid:<9} {os.path.basename(cwd)[:28]:<28} "
              f"{u['turns']:>5} {u['etok']:>12,} {raw:>12,} {u['etok'] * USD_PER_MTOK / 1e6:>7.2f}")
    if len(rows) >= 2:
        a, b = rows[-2][3]["etok"], rows[-1][3]["etok"]
        hi, lo = max(a, b), min(a, b)
        print(f"\nLast two sessions: {100 * (1 - lo / hi):.0f}% fewer effective tokens in the cheaper one.")


def statusline():
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        ev = {}
    cwd = (ev.get("workspace") or {}).get("current_dir") or ev.get("cwd", "")
    sess = load(cwd).get(ev.get("session_id", ""))
    if not sess:
        print("TF off")
        return
    s, _ = spent(sess, ev.get("transcript_path", ""))
    pct = min(1.0, s / sess["budget"])
    bar = "#" * int(pct * 10) + "-" * (10 - int(pct * 10))
    print(f"TF [{bar}] {fmt(s)}/{fmt(sess['budget'])} etok {pct * 100:.0f}% "
          f"~${s * USD_PER_MTOK / 1e6:.2f} | {sess['phase']}")


def main():
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")  # Windows defaults to cp1252
        except (AttributeError, ValueError):
            pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    hooks = {"hook-prompt": hook_prompt, "hook-pretool": hook_pretool,
             "hook-posttool": hook_posttool, "hook-stop": hook_stop}
    if cmd in hooks:
        try:
            ev = json.load(sys.stdin)
        except ValueError:
            sys.exit(0)
        try:
            hooks[cmd](ev)
        except SystemExit:
            raise
        except Exception as e:  # a broken hook must never block the user
            eprint(f"tokenforward: {e}")
            sys.exit(0)
    elif cmd == "sessions":
        cmd_sessions(sys.argv[2:])
    elif cmd == "plan":
        cmd_plan(sys.argv[2:])
    elif cmd == "statusline":
        statusline()
    elif cmd == "status":
        print(json.dumps(load(os.getcwd()), indent=1))
    elif cmd == "off":
        save(os.getcwd(), {})
        print("TokenForward budgets cleared.")
    else:
        eprint(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
