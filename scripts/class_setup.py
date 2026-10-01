#!/usr/bin/env python3
"""One-shot class setup, cross-platform. Called by setup.ps1 / setup.sh after prerequisites exist.

Does: Claude Code plugins (tokenforward, ponytail), statusline, a demo repo (pandas or numpy) with a
prebuilt-wheel test env and run_tests.py, the graphify code graph, the demo spec, and a planner smoke test.
Safe to re-run.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

TF_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMOS = {
    "pandas": {"repo": "https://github.com/pandas-dev/pandas.git", "ref": "v3.0.6", "version": "3.0.6",
               "ticket": "pandas_str_truncate", "smoke": "pandas/tests/strings/test_strings.py -k removeprefix -q"},
    "numpy": {"repo": "https://github.com/numpy/numpy.git", "ref": "v2.4.6", "version": "2.4.6",
              "ticket": "numpy_average_where", "smoke": "numpy/lib/tests/test_function_base.py -k average -q"},
}
WIN = os.name == "nt"


def step(msg):
    print(f"\n== {msg}", flush=True)


def run(cmd, cwd=None, check=True):
    exe = shutil.which(cmd[0]) or cmd[0]
    r = subprocess.run([exe, *cmd[1:]], cwd=cwd, text=True, encoding="utf-8", errors="replace",
                       capture_output=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:])
        raise SystemExit(f"FAILED: {' '.join(cmd)}")
    return r


def plugins():
    step("Claude Code plugins")
    for mkt, plugin in (("sayonsom/tokenforward", "tokenforward@tokenforward"),
                        ("DietrichGebert/ponytail", "ponytail@ponytail")):
        r = run(["claude", "plugin", "marketplace", "add", mkt], check=False)
        print(f"  marketplace {mkt}: {'ok' if r.returncode == 0 else (r.stderr or r.stdout).strip()[:120]}")
        r = run(["claude", "plugin", "install", plugin], check=False)
        print(f"  install {plugin}: {'ok' if r.returncode == 0 else (r.stderr or r.stdout).strip()[:120]}")


def statusline():
    step("Statusline")
    p = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    try:
        s = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    launcher = os.path.join(TF_ROOT, "scripts", "tf-launch.js").replace("\\", "/")
    if "statusLine" in s and "tf-launch.js" not in json.dumps(s["statusLine"]):
        print("  you already have a statusLine; left it alone. TokenForward's is:")
        print(f'  "statusLine": {{"type": "command", "command": "node \\"{launcher}\\" statusline"}}')
        return
    s["statusLine"] = {"type": "command", "command": f'node "{launcher}" statusline'}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    print(f"  set in {p}")


def demo(name, work):
    d = DEMOS[name]
    repo = os.path.join(work, name)
    env = os.path.join(work, f"{name}-env")
    py = os.path.join(env, "Scripts" if WIN else "bin", "python.exe" if WIN else "python")

    step(f"Demo repo: {name} {d['ref']} (shallow clone, a few minutes)")
    if not os.path.exists(repo):
        run(["git", "clone", "-q", "-c", "core.autocrlf=false", "--depth", "1", "--branch", d["ref"], d["repo"], repo])
    else:
        print("  exists, reusing")

    step(f"Prebuilt {name} {d['version']} test env (no compile)")
    if not os.path.exists(py):
        run(["uv", "venv", "-q", "--python", "3.12", env])
    run(["uv", "pip", "install", "-q", "--python", py, f"{name}=={d['version']}", "pytest", "hypothesis", "tzdata"])
    site = run([py, "-c", f"import {name} as m, os; print(os.path.dirname(os.path.dirname(m.__file__)))"],
               cwd=os.path.abspath(os.sep)).stdout.strip()

    step("run_tests.py, spec.md, baseline tag")
    tpl = open(os.path.join(TF_ROOT, "bench", "tickets", "run_tests_template.py"), encoding="utf-8").read()
    tpl = tpl.replace("__WHEEL_SITE__", site).replace("__PYTHON__", py) \
             .replace("__NP_VERSION__", d["version"]).replace("__PKG__", name)
    with open(os.path.join(repo, "run_tests.py"), "w", encoding="utf-8") as f:
        f.write(tpl)
    shutil.copy(os.path.join(TF_ROOT, "bench", "tickets", d["ticket"], "TICKET.md"), os.path.join(repo, "spec.md"))
    excl = os.path.join(repo, ".git", "info", "exclude")
    if ".overlay/" not in open(excl, encoding="utf-8").read():
        with open(excl, "a", encoding="utf-8") as f:
            f.write("\n.overlay/\ngraphify-out/\n.tokenforward/\nrun_tests.py\nspec.md\n")
    run(["git", "tag", "-f", "bench-base"], cwd=repo)

    step("graphify code graph (AST only, 0 tokens, ~30 s)")
    run(["graphify", "extract", repo, "--code-only"], cwd=work)   # outside the tree: the source shadows the package
    run(["graphify", "claude", "install"], cwd=repo, check=False)

    step("Smoke tests")
    r = run([py, "run_tests.py", *d["smoke"].split()], cwd=repo, check=False)
    print("  tests:", (r.stdout.strip().splitlines() or ["?"])[-1])
    r = run(["node", os.path.join(TF_ROOT, "scripts", "tf-launch.js"), "plan", "150k", "spec.md", "--dry"], cwd=repo)
    print("  planner:", [l for l in r.stdout.splitlines() if l.startswith("Fits:")][0])
    return repo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=os.path.join(os.path.expanduser("~"), "tfd-class"))
    ap.add_argument("--demo", default="pandas", choices=sorted(DEMOS) + ["none"])
    ap.add_argument("--skip-plugins", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    if not a.skip_plugins:
        plugins()
    statusline()
    repo = demo(a.demo, a.work) if a.demo != "none" else None
    step("Ready")
    if repo:
        print(f"  cd {repo}")
    print("  claude")
    print("  /tfd-plan 150k spec.md      what fits, 0 tokens")
    print("  /tfd 150k spec.md           implement what fits, get a changelog")


if __name__ == "__main__":
    main()
