# Spec-Driven Development Without the Token Bill: 30-minute class

Audience: senior engineers, $30/month API credits, on Spec Kit, saying SDD burns tokens.
What they should leave believing: the spec was never the expensive part. Re-reading instructions, re-reading generated docs and unbounded exploration are. Keep the spec, plan it for free, execute it under a budget.
Numbers on screen come only from your pre-class run. Do not quote numbers you have not measured.

## The engineer's workflow (what you teach)

```
1. Write or change the spec        specs/012-x/spec.md or tasks.md (Spec Kit) or any markdown list
2. /tfd-plan 150k <spec>           what fits in 150k? zero tokens, a table per item, nothing changes
3. /tfd 150k <spec>                implements only the admitted items, in order, under a hard budget
4. Read the changelog              Done / Deferred / Files / Tests + measured spend, also appended to .tokenforward/CHANGELOG.md
5. Deferred items                  next session: /tfd 150k <spec> again, or raise the budget
```
Changed spec only: add `--since main`. The planner reads only the added lines.
Keep Spec Kit for thinking (specify, plan, tasks) and let TokenForward do `implement`: `/tfd 200k specs/012-x/tasks.md`.

## The demo task

numpy v2.4.6 (~272k Python + ~384k C LOC). Spec: `bench/tickets/numpy_average_where/TICKET.md`, 10 items: add `where=` to `np.average` and `np.ma.average` (weights, returned, keepdims, empty slices, masked arrays, `__array_function__` dispatcher, all 26 type-stub overloads, docstrings, release note).
It is pure Python, so there is no C build. `run_tests.py` overlays changed files onto a prebuilt numpy wheel; numpy's own tests for these modules run in ~6 s.
Scoring: 18 hidden acceptance tests plus numpy's own `test_function_base.py` and `ma/tests/test_extras.py`. Reference solution: 18/18, 0 regressions. Unmodified numpy: 1/18.

Planner on this spec (graphify locator, uncalibrated, for rehearsal; your run replaces these):
- 60k: nothing fits. The fixed session cost alone is ~34k. This is the minimum viable budget lesson.
- 150k: 6 of 10 items admitted, stubs/docs/tests deferred.
- 400k: 10 of 10, estimate ~212k.
The type-stub item is the most expensive (26 overloads). Engineers recognise that.

## Your steps, in order

On the Windows demo machine (no Docker needed):
1. Install: Git for Windows, Node LTS, Python 3.11+, uv (`winget install astral-sh.uv`), Claude Code. Then `git config --global core.longpaths true`.
2. Unzip `tokenforward`, push it to GitHub as `<you>/tokenforward`.
3. Tools: `uv tool install graphifyy` and `uv tool install specify-cli`.
4. Scoring env (PowerShell):
   ```
   uv venv $HOME\npbench
   $env:VIRTUAL_ENV="$HOME\npbench"; uv pip install numpy==2.4.6 pytest hypothesis
   ```
5. Smoke test (cheap, ~minutes):
   ```
   python bench\run_bench.py --arms tfd-graph --model haiku --skip-regress --python $HOME\npbench\Scripts\python.exe
   ```
   Open `bench\results\<stamp>\report.html`. If it fails, the log line says which step; fix before noon.
6. Real run (start by late morning; each arm is a full agent session):
   ```
   python bench\run_bench.py --arms speckit,tfd-bare,tfd-graph,speckit-tfd --model sonnet --budget 400k --python $HOME\npbench\Scripts\python.exe
   ```
   Watch `total_cost_usd` after the first arm. Screenshot the report KPI tiles.
7. Live demo repo: copy `bench\work\base-numpy` to e.g. `C:\demo\numpy`, run `graphify extract C:\demo\numpy --code-only` from outside that folder, then `graphify claude install` inside it. Start Claude Code there with TokenForward installed and the statusline on. Copy `TICKET.md` in as `spec.md`.
8. Rehearse once: `/tfd-plan 60k spec.md`, `/tfd-plan 150k spec.md`, `/tfd-plan 400k spec.md`, then `/tfd 150k spec.md` for a few minutes.

## Run of show (30 min)

| Min | Segment | On screen |
|---|---|---|
| 0-3 | The bill | Cost = sum over turns of context size. Turn 1 at 24k, turn 40 at 100k. Output is a sliver. |
| 3-7 | Where Spec Kit spends | ~19k words of skill instructions loaded across phases; spec, plan and tasks docs written and then read back; `implement` explores without a limit. Show `specs/` line count from the pre-run vs code lines. |
| 7-11 | Planning is free | Terminal, no Claude: `node scripts\tf-launch.js plan 60k spec.md --dry`, then 150k, then 400k. The table appears in under a second. Point at marginal cost rising per item: context accumulates. |
| 11-19 | Implement under budget | `/tfd 150k spec.md`. Narrate: plan adopted, spec card, a denied whole-file read of `_function_base_impl.py` (5,760 lines), ranged reads, phase flips, statusline. Let it finish or stop at verify. |
| 19-22 | The changelog | Final reply: Done / Deferred / Files / Tests. `type .tokenforward\CHANGELOG.md` shows the measured spend next to the planned number. |
| 22-27 | The benchmark | `report.html`: % fewer tokens vs Spec Kit for TokenForward and TokenForward + graphify, acceptance per arm, regressions. Then `speckit-tfd`: they can keep Spec Kit and still save. |
| 27-30 | Adoption | Install lines. The rule: every task starts with a spec and a number. `/tfd-plan` before `/tfd`. |

## Pushback answers

- "The planner is a guess": yes, a model of the loop, calibrated per repo. Show calibration.json after the demo run: planned vs actual.
- "Budget made it stop early": that is the point of deferral. Deferred items are listed, not silently dropped.
- "You excluded Spec Kit setup": deliberately, in its favour.
- "n=1": say it first; `--runs 3` for medians.

## Fallbacks

- Live run slow or API trouble: the planner demo needs no API at all. Show the pre-run report and a receipt.
- Hook not firing: `claude --debug` shows hook runs. `node scripts\tf-launch.js status` in the repo shows state. `TF_PYTHON=C:\path\python.exe` if Python detection fails.
- Smaller backup tickets on httpx: `--ticket retry_transport` (9 tests), `--ticket client_retries` (18 tests).

## Windows notes

- Hooks run through cmd.exe, so every hook calls `node tf-launch.js`, which finds Python (`python3`, `python`, `py -3`, or `TF_PYTHON`) and skips the Microsoft Store stub.
- The harness never uses a shell; paths and prompts pass safely. If `claude` is an npm `.cmd` shim, prompts go on stdin.
- Spec Kit helper scripts default to `sh`, which runs in Claude Code's Git Bash. If Spec Kit misbehaves, add `--speckit-script ps`.
- Untested on Windows by me; step 5 is there to catch surprises early.
