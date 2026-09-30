#!/usr/bin/env python3
"""Three-arm token benchmark on a real brownfield repo (httpx).

Arms (same ticket, same model, same hidden acceptance tests):
  vibe     one prompt, no process
  speckit  GitHub Spec Kit: constitution -> specify -> plan -> tasks -> implement
  tfd      TokenForward + graphify (AST graph, 0 LLM tokens) + ponytail

Usage:
  python bench/run_bench.py --arms vibe,speckit,tfd --model sonnet --budget 250k --runs 1
  python bench/run_bench.py --report-only bench/results/<stamp>
Needs: claude CLI authenticated (ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN), git,
specify (spec-kit), graphify (graphifyy). Run inside the Docker image for clean isolation.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import tf  # noqa: E402  reuse the exact same token accounting as the plugin

REPO = "https://github.com/encode/httpx.git"
COMMIT = "b5addb64f0161ff6bfe94c124ef76f6a1fba5254"
PONYTAIL = "https://github.com/DietrichGebert/ponytail.git"
TICKET = open(os.path.join(HERE, "TICKET.md")).read().strip()
ACCEPT_N = open(os.path.join(HERE, "acceptance", "test_retry_acceptance.py")).read().count("\ndef test_")
HEADLESS = "\n\nThis is a non-interactive run. Do not ask questions; make reasonable assumptions and finish the work."

SPECKIT_STEPS = [
    "/speckit-constitution Keep changes minimal and consistent with existing httpx conventions. Every feature ships with tests.",
    "/speckit-specify " + TICKET,
    "/speckit-plan Python 3.9+, stdlib only, follow the existing httpx transport patterns.",
    "/speckit-tasks",
    "/speckit-implement",
]


def sh(cmd, cwd=None, env=None, timeout=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, text=True,
                       capture_output=True, shell=isinstance(cmd, str))
    if check and r.returncode != 0:
        raise RuntimeError(f"{cmd}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------- prepare ----------------

def prepare(work):
    base = os.path.join(work, "base")
    if not os.path.exists(base):
        log("cloning httpx @", COMMIT[:8])
        sh(["git", "clone", "-q", REPO, base])
        sh(["git", "checkout", "-q", COMMIT], cwd=base)
    pt = os.path.join(work, "ponytail")
    if not os.path.exists(pt):
        sh(["git", "clone", "-q", "--depth", "1", PONYTAIL, pt])
    return base, pt


def failing(repo, paths, py):
    env = dict(os.environ, PYTHONPATH=repo)
    r = sh([py, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", *paths],
           cwd=repo, env=env, check=False, timeout=900)
    fails = set(re.findall(r"^(?:FAILED|ERROR) (\S+)", r.stdout, re.M))
    m = re.search(r"(\d+) passed", r.stdout)
    return fails, int(m.group(1)) if m else 0, r.stdout[-600:]


def new_arm_dir(work, base, name):
    d = os.path.join(work, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    shutil.copytree(base, d, symlinks=True)
    with open(os.path.join(d, ".git", "info", "exclude"), "a") as f:
        f.write("\ngraphify-out/\n.tokenforward/\n")
    return d


def commit_scaffold(d, msg):
    sh("git add -A && git -c user.email=b@b -c user.name=bench commit -qm '%s' --allow-empty" % msg, cwd=d)
    return sh(["git", "rev-parse", "HEAD"], cwd=d).stdout.strip()


# ---------------- run claude ----------------

def claude(prompt, cwd, model, extra=(), resume=None, timeout=2400, env=None):
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model,
           "--dangerously-skip-permissions", *extra]
    if resume:
        cmd += ["--resume", resume]
    t0 = time.time()
    r = sh(cmd, cwd=cwd, env=env, timeout=timeout, check=False)
    try:
        j = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        j = {"is_error": True, "result": (r.stdout + r.stderr)[-1500:]}
    j["_wall_s"] = round(time.time() - t0, 1)
    return j


def transcript_for(sid):
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    return hits[0] if hits else ""


def summarize_calls(calls):
    tot = {"cost_usd": 0.0, "turns": 0, "wall_s": 0.0, "errors": 0,
           "input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    sids = []
    for j in calls:
        tot["cost_usd"] += j.get("total_cost_usd") or 0
        tot["turns"] += j.get("num_turns") or 0
        tot["wall_s"] += j.get("_wall_s") or 0
        tot["errors"] += 1 if j.get("is_error") else 0
        if j.get("session_id") and j["session_id"] not in sids:
            sids.append(j["session_id"])
    # Token breakdown from the transcripts (includes subagents), same math as the plugin.
    for sid in sids:
        u = tf.usage(transcript_for(sid))
        for k in ("input", "cache_write", "cache_read", "output"):
            tot[k] += u[k]
    if not any(tot[k] for k in ("input", "cache_write", "cache_read", "output")):
        for j in calls:  # fallback: CLI-reported usage
            u = j.get("usage") or {}
            tot["input"] += u.get("input_tokens", 0)
            tot["cache_write"] += u.get("cache_creation_input_tokens", 0)
            tot["cache_read"] += u.get("cache_read_input_tokens", 0)
            tot["output"] += u.get("output_tokens", 0)
    tot["etok"] = int(tot["input"] + 1.25 * tot["cache_write"] + 0.1 * tot["cache_read"] + 5 * tot["output"])
    tot["total_tokens"] = tot["input"] + tot["cache_write"] + tot["cache_read"] + tot["output"]
    tot["cost_usd"] = round(tot["cost_usd"], 4)
    tot["session_ids"] = sids
    return tot


def run_arm(arm, work, base, pt, a):
    d = new_arm_dir(work, base, f"{arm}-r{a.run_idx}")
    extra, env = [], dict(os.environ)
    if arm == "speckit":
        sh(["specify", "init", "--here", "--force", "--non-interactive",
            "--integration", "claude", "--script", "sh"], cwd=d)
    if arm == "tfd":
        sh(["graphify", "extract", ".", "--code-only"], cwd=d)
        sh(["graphify", "claude", "install"], cwd=d, check=False)
        extra = ["--plugin-dir", ROOT, "--plugin-dir", pt]
        env.update(TF_PONYTAIL="1", TF_USD_PER_MTOK_IN=str(a.usd_per_mtok))
    head = commit_scaffold(d, f"{arm} scaffold")

    log(f"[{arm}] running in {d}")
    calls = []
    if arm == "vibe":
        calls.append(claude(TICKET + HEADLESS, d, a.model))
    elif arm == "speckit":
        sid = None
        for step in SPECKIT_STEPS:
            j = claude(step + HEADLESS, d, a.model, resume=sid)
            calls.append(j)
            sid = j.get("session_id") or sid
            log(f"[speckit] {step.split()[0]} ${j.get('total_cost_usd', 0):.3f} turns={j.get('num_turns')}")
    elif arm == "tfd":
        prompt = (f"/tokenforward:tfd {a.budget} " if a.tfd_slash else f"Budget: max {a.budget} tokens.\n\n") + TICKET
        calls.append(claude(prompt + HEADLESS, d, a.model, extra=extra, env=env))

    res = summarize_calls(calls)
    res.update(arm=arm, run=a.run_idx, dir=d, model=a.model)

    # Score: hidden acceptance tests, regressions vs baseline, diff size.
    acc_fail, acc_pass, _ = failing(d, [os.path.join(HERE, "acceptance")], a.python)
    res["acceptance_pass"], res["acceptance_total"] = min(acc_pass, ACCEPT_N), ACCEPT_N
    if not a.skip_regress:
        f, _, _ = failing(d, ["tests"], a.python)
        res["regressions"] = sorted(f - a.baseline_fail)
    sh("git add -A", cwd=d)
    ns = sh(["git", "diff", "--cached", "--numstat", head], cwd=d).stdout
    src = tests = spec_docs = 0
    files = []
    for line in ns.splitlines():
        add, _, path = line.split("\t", 2)
        if add == "-":
            continue
        if path.startswith(("specs/", ".specify/memory")):
            spec_docs += int(add)
            continue
        if path.startswith((".specify", ".claude", "CLAUDE.md", "graphify-out")):
            continue
        files.append(path)
        if "test" in path:
            tests += int(add)
        else:
            src += int(add)
    res.update(loc_src=src, loc_tests=tests, spec_doc_lines=spec_docs, files_changed=files)
    receipts = glob.glob(os.path.join(d, ".tokenforward", "receipts", "*.json"))
    if receipts:
        res["tf_receipt"] = json.load(open(receipts[0]))
    res["result_tail"] = str(calls[-1].get("result", ""))[-800:]
    return res


# ---------------- report ----------------

LIGHT = dict(bg="#FFFFFF", panel="#F5F7FA", grid="#E5E7EB", axis="#D1D5DB", t1="#111827", t2="#4B5563",
             s=["#7A2E2E", "#C69214", "#003A8F"])
DARK = dict(bg="#0B1220", panel="#111827", grid="#1F2933", axis="#374151", t1="#E5E7EB", t2="#9CA3AF",
            s=["#C26D6D", "#E0B84C", "#4F83CC"])
ARM_LABEL = {"vibe": "Vibe coding", "speckit": "Spec Kit SDD", "tfd": "TokenForward + graphify + ponytail"}


def aggregate(rows):
    by = {}
    for r in rows:
        by.setdefault(r["arm"], []).append(r)
    agg = {}
    for arm, rs in by.items():
        med = lambda k: sorted(x.get(k, 0) or 0 for x in rs)[len(rs) // 2]  # noqa: E731
        agg[arm] = {k: med(k) for k in ("cost_usd", "etok", "total_tokens", "turns", "wall_s",
                                          "loc_src", "loc_tests", "acceptance_pass", "acceptance_total",
                                          "cache_read", "output", "spec_doc_lines")}
        agg[arm]["regressions"] = max(len(x.get("regressions", [])) for x in rs)
        agg[arm]["n"] = len(rs)
    return agg


def report(outdir):
    rows = json.load(open(os.path.join(outdir, "results.json")))["runs"]
    agg = aggregate(rows)
    arms = [a for a in ("vibe", "speckit", "tfd") if a in agg]
    metrics = [("cost_usd", "Cost (USD)", "${:.2f}"), ("etok", "Effective tokens", "{:,.0f}"),
               ("total_tokens", "Raw tokens incl. cache reads", "{:,.0f}"), ("turns", "Agent turns", "{:.0f}"),
               ("wall_s", "Wall time (s)", "{:.0f}"), ("loc_src", "Source LOC added", "{:.0f}")]

    def bars(key, fmtspec):
        vals = [agg[a][key] for a in arms]
        mx = max(vals) or 1
        out = []
        for i, a in enumerate(arms):
            w = 100 * vals[i] / mx
            out.append(f'<div class="row"><span class="lbl">{ARM_LABEL[a]}</span>'
                       f'<span class="track"><span class="bar s{i}" style="width:{w:.1f}%"></span></span>'
                       f'<span class="val">{fmtspec.format(vals[i])}</span></div>')
        return "".join(out)

    cards = "".join(f'<section class="card"><h3>{title}</h3>{bars(k, f)}</section>' for k, title, f in metrics)
    head = ""
    if "vibe" in agg and "tfd" in agg and agg["tfd"]["cost_usd"]:
        x_v = agg["vibe"]["cost_usd"] / agg["tfd"]["cost_usd"]
        x_s = agg.get("speckit", {}).get("cost_usd", 0) / agg["tfd"]["cost_usd"]
        head = (f"<p class='lead'>TokenForward cost {x_v:.1f}x less than vibe coding"
                + (f" and {x_s:.1f}x less than Spec Kit" if x_s else "") + " on the same ticket.</p>")
    trs = "".join(
        f"<tr><td>{ARM_LABEL[a]}</td><td>{agg[a]['acceptance_pass']}/{agg[a]['acceptance_total']}</td>"
        f"<td>{agg[a]['regressions']}</td><td>{agg[a]['loc_tests']}</td><td>{agg[a]['spec_doc_lines']}</td><td>{agg[a]['n']}</td></tr>" for a in arms)
    model = rows[0].get("model", "") if rows else ""

    def css(p):
        return (f"--bg:{p['bg']};--panel:{p['panel']};--grid:{p['grid']};--axis:{p['axis']};"
                f"--t1:{p['t1']};--t2:{p['t2']};--s0:{p['s'][0]};--s1:{p['s'][1]};--s2:{p['s'][2]};")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Token Benchmark</title><style>
:root{{{css(LIGHT)}}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{{css(DARK)}}}}}
:root[data-theme="dark"]{{{css(DARK)}}}
body{{margin:0;background:var(--bg);color:var(--t1);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:960px;margin:0 auto;padding:32px 16px}}
h1{{font-size:26px;margin:0 0 4px}} .sub{{color:var(--t2);margin:0 0 16px}} .lead{{font-size:18px;font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
.card{{background:var(--panel);border:1px solid var(--grid);border-radius:10px;padding:14px 16px}}
.card h3{{margin:0 0 10px;font-size:13px;color:var(--t2);font-weight:600;text-transform:uppercase;letter-spacing:.04em}}
.row{{display:grid;grid-template-columns:1fr;gap:2px;margin-bottom:10px}}
.lbl{{font-size:12px;color:var(--t2)}} .track{{display:block;height:14px;background:var(--grid);border-radius:3px}}
.bar{{display:block;height:100%;border-radius:3px}} .s0{{background:var(--s0)}} .s1{{background:var(--s1)}} .s2{{background:var(--s2)}}
.val{{font-variant-numeric:tabular-nums;font-size:13px}}
table{{width:100%;border-collapse:collapse;margin-top:16px;font-variant-numeric:tabular-nums}}
td,th{{text-align:left;padding:8px;border-bottom:1px solid var(--grid)}} th{{color:var(--t2);font-weight:600;font-size:13px}}
.note{{color:var(--t2);font-size:13px;margin-top:16px}}
</style></head><body><main>
<h1>Same ticket, three workflows</h1>
<p class="sub">httpx @ {COMMIT[:8]} (~8.8k LOC) · ticket: RetryTransport · model: {model} · median of runs</p>
{head}
<div class="grid">{cards}</div>
<table><tr><th>Arm</th><th>Hidden acceptance</th><th>Regressions</th><th>Test LOC</th><th>Spec doc lines</th><th>Runs</th></tr>{trs}</table>
<p class="note">Effective tokens = input + 1.25 x cache write + 0.1 x cache read + 5 x output (input-token equivalents, proportional to USD).
Cost is the CLI's own total_cost_usd. Acceptance tests were never shown to any arm.</p>
</main></body></html>"""
    p = os.path.join(outdir, "report.html")
    open(p, "w").write(html)
    log("report:", p)
    for a in arms:
        g = agg[a]
        log(f"  {a:8s} ${g['cost_usd']:.2f}  etok={g['etok']:,}  turns={g['turns']}  "
            f"accept={g['acceptance_pass']}/{g['acceptance_total']}  regress={g['regressions']}  src_loc={g['loc_src']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="vibe,speckit,tfd")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--budget", default="250k")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--work", default=os.path.join(HERE, "work"))
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--usd-per-mtok", type=float, default=3.0)
    ap.add_argument("--tfd-slash", action="store_true", help="invoke /tokenforward:tfd instead of a budget sentence")
    ap.add_argument("--skip-regress", action="store_true")
    ap.add_argument("--report-only")
    a = ap.parse_args()
    if a.report_only:
        return report(a.report_only)

    os.makedirs(a.work, exist_ok=True)
    base, pt = prepare(a.work)
    a.baseline_fail = set()
    if not a.skip_regress:
        a.baseline_fail, n, _ = failing(base, ["tests"], a.python)
        log(f"baseline: {n} passed, {len(a.baseline_fail)} pre-existing failures (ignored)")
    outdir = os.path.join(HERE, "results", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(outdir)
    rows = []
    for i in range(a.runs):
        a.run_idx = i
        for arm in a.arms.split(","):
            r = run_arm(arm, a.work, base, pt, a)
            rows.append(r)
            log(f"[{arm}] ${r['cost_usd']:.3f} etok={r['etok']:,} accept={r['acceptance_pass']}/{r['acceptance_total']}")
            json.dump({"ticket": TICKET, "commit": COMMIT, "runs": rows},
                      open(os.path.join(outdir, "results.json"), "w"), indent=1)
    report(outdir)


if __name__ == "__main__":
    main()
