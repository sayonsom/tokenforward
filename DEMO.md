# TokenForward Live Demo: Spec-Driven Development on pandas

Goal for the room: the same spec, implemented twice on pandas, side by side. Plain Claude Code on the left, TokenForward on the right. At the end, one command prints both sessions' token totals and the percentage saved.

Spec: `Series.str.truncate(width, side, placeholder)` in pandas 3.0.6. It has 8 items covering the string accessor, both string storages, `Index`, docstrings, reference docs, whatsnew and tests. The file is `spec.md` in the demo folder.

---

## 0. Before you start talking (2 min)

Run the setup if you have not already (PowerShell):
```powershell
irm https://raw.githubusercontent.com/sayonsom/tokenforward/main/setup.ps1 | iex
```
It ends with a `Fits:` line from the planner. That means everything works.

Make the plain copy (same commit, no graph, no TokenForward budget):
```powershell
cd $HOME\tfd-class\pandas
git worktree add ..\pandas-plain bench-base
Copy-Item run_tests.py, spec.md ..\pandas-plain\
```

Open two terminals side by side:
- Left: `cd $HOME\tfd-class\pandas-plain`
- Right: `cd $HOME\tfd-class\pandas`

---

## 1. Start both runs early (minute 3)

Start both now. They run while you teach, and you compare them at the end.

Left terminal, plain Claude Code:
```powershell
claude --dangerously-skip-permissions
```
```
Implement every item in spec.md.
```

Right terminal, TokenForward:
```powershell
claude --dangerously-skip-permissions
```
```
/tfd 350k spec.md
```

Say to the room: "Same model, same spec, same commit. 350k is what the planner says the whole spec needs, so both sides do all 8 items. Nothing is deferred, so the comparison is fair."

Note: `--dangerously-skip-permissions` is for these throwaway demo folders only, so neither side stops for approvals. Ponytail is installed globally, so it is active on both sides. The difference measured is TokenForward plus graphify.

---

## 2. While they run: the bill (minutes 4-8)

Point at the right terminal's status line: `TF [###-------] 98k/350k etok 28% ~$0.29 | map`.

Teach:
- An agent turn re-sends the whole context. Cost is the sum over turns of context size.
- Turn 1 is about 24k tokens. Turn 40 is about 100k. Output tokens are a sliver.
- So the two levers are fewer turns and a smaller context. Every line read is paid again on every later turn.
- `accessor.py` is 4,885 lines. One whole-file read is about 50k tokens, re-paid on every turn after it.

Watch the right terminal for this message, and read it out when it appears:
`TokenForward: accessor.py has 4885 lines (... paid again on every later turn). Locate with Grep -n or graphify query then Read with offset/limit <= 120.`

---

## 3. Planning is free (minutes 8-13)

Open a third terminal (no Claude, no API):
```powershell
cd $HOME\tfd-class\pandas
node ..\tokenforward\scripts\tf-launch.js plan 80k spec.md --dry
node ..\tokenforward\scripts\tf-launch.js plan 150k spec.md --dry
node ..\tokenforward\scripts\tf-launch.js plan 350k spec.md --dry
```

What you will see (measured on this repo, uncalibrated):

| Budget | Items that fit | Point to make |
|---|---|---|
| 80k | 0 of 8 | A session costs ~34k before any work. There is a minimum viable budget. |
| 150k | 3 of 8 | The core method fits; storage backends, docs and tests are deferred and listed, not dropped. |
| 350k | 8 of 8 | The whole spec is estimated at ~323k. |

Say: "That took under a second and used zero tokens. It found the code with graphify, sized every function from real line counts, and simulated the agent loop. This is the part Spec Kit pays an LLM for."

Point at the Marginal column: items get more expensive as you go down, because context accumulates. Item 4 (two string storages) and item 7 (docs) are the costly ones. Engineers recognise that.

---

## 4. Spec-driven, without the documents (minutes 13-18)

Scroll the right terminal to the top and show:
1. The plan table it printed (same planner, now arming the budget).
2. The 8-line spec card: Goal / Interface / Touch / Acceptance / Out of scope. No spec.md rewrite, no plan.md, no tasks.md.
3. Tests written first. The tests are the executable spec, and they end the loop.
4. Ranged reads (`offset`/`limit`) instead of whole files.
5. The phase change: `map` to `build` on the first edit, `build` to `verify` on the first `python run_tests.py`.

Contrast with the left terminal: scroll it and count the whole-file reads.

Say: "SDD was never the expensive part. Re-loading instructions, re-reading generated docs and unbounded exploration were. Keep the spec. Plan it for free. Execute it under a number."

---

## 5. The changelog (minute ~20, when the right side finishes)

The right terminal's final reply is the changelog:
```
Done: 1-8 | Deferred: none | Files: pandas/core/strings/accessor.py, ... | Tests: N/N python run_tests.py pandas/tests/strings/test_strings.py -k truncate
```
Show the record with measured spend next to the planned number:
```powershell
type .tokenforward\CHANGELOG.md
```
Run the tests yourself to prove it:
```powershell
python run_tests.py pandas/tests/strings/test_strings.py -k truncate -q
```

---

## 6. The proof: token savings (minutes 22-26)

When both sides are done (or at minute 24, whichever comes first), in the third terminal:
```powershell
node $HOME\tfd-class\tokenforward\scripts\tf-launch.js sessions $HOME\tfd-class\pandas-plain $HOME\tfd-class\pandas
```
Output shape:
```
when   session   folder         turns  eff. tokens   raw tokens    ~USD
16:12  3f2a...   pandas-plain      ..        .....        .....    ....
16:12  9c1b...   pandas            ..        .....        .....    ....

Last two sessions: NN% fewer effective tokens in the cheaper one.
```
Read the three numbers out loud: turns, effective tokens, USD. Then run the tests in both folders:
```powershell
cd $HOME\tfd-class\pandas-plain; python run_tests.py pandas/tests/strings/test_strings.py -k truncate -q
cd $HOME\tfd-class\pandas;       python run_tests.py pandas/tests/strings/test_strings.py -k truncate -q
```
The claim is fewer tokens, with the spec done and tests passing.

If the left side is still running at minute 24, run the `sessions` command anyway. The left total only goes up from there, so the saving shown is a floor. Say so.

Effective tokens = input + 1.25 x cache write + 0.1 x cache read + 5 x output. These are input-token equivalents, proportional to USD for every Claude model.

---

## 7. Students try it (minutes 26-29)

After setup has finished on their machines:
```
cd ~/tfd-class/pandas
claude
/tfd-plan 150k spec.md
/tfd 100k spec.md
```
Then `type .tokenforward\CHANGELOG.md` (Windows) or `cat .tokenforward/CHANGELOG.md`.

## 8. Close (minute 29-30)

The rule: every task starts with a spec and a number. `/tfd-plan` before `/tfd`. Keep Spec Kit for thinking if you like; hand `tasks.md` to `/tfd` for doing.

---

## If something goes wrong

| Problem | Do this |
|---|---|
| Live runs too slow | Skip to step 3 (planner, no API). Run `sessions` at minute 24; it reports the floor. |
| Status line shows `TF off` | The budget was not armed. Type: `run node "<path>/tokenforward/scripts/tf-launch.js" plan 350k spec.md` in that Claude session. |
| Hook errors mentioning Python | Set `$env:TF_PYTHON = "C:\path\to\python.exe"` and restart `claude`. |
| `sessions` finds nothing | Pass the exact folders you ran `claude` in. It looks at the last 3 days of sessions. |
| Budget blocks before item 8 | That is the feature: point at the Deferred list. Rerun `/tfd 150k spec.md` to finish. |
| A student's setup fails | The planner demo needs only Node and Python: `node tokenforward\scripts\tf-launch.js plan 150k spec.md --dry`. |
