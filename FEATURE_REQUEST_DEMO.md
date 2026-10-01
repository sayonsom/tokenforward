# Demo: A Feature Request Lands. How a Developer Reacts, Economically.

The story for the room: an issue arrives on pandas. Watch the developer go from issue to merged change while spending tokens only where they buy code. Every step shows what it costs.

Folder: `$HOME\tfd-class\pandas` (created by the setup script). Second folder for the comparison: `$HOME\tfd-class\pandas-plain`.

---

## The incoming request (show this on screen)

> **Feature request: a way to shorten long strings for display**
>
> I format reports with `Series` of product names. Long names break my tables. Today I write
> `s.map(lambda x: x if len(x) <= 20 else x[:17] + "...")`, which breaks on NaN and is slow on
> pyarrow strings. Could pandas have `s.str.truncate(20)`? Sometimes I need to keep the end
> (file paths) or both ends (IDs).

Ask the room: "What does a developer do first?" Most will say "open Claude and ask it to implement it." That is the expensive answer.

---

## Step 1. Triage, zero tokens (1 min)

The developer answers three questions without an LLM:
- Is it in scope? Yes: it is a string accessor method, like `str.wrap` and `str.removeprefix`.
- Where does it live? Ask the graph, not the model:
  ```powershell
  graphify query "where is str.wrap implemented for object and arrow strings"
  ```
  It returns `accessor.py`, `object_array.py` and `_arrow_string_mixins.py` with line numbers. No file was read.
- What are the hidden obligations in this repo? Both string storages, `Index`, docstring style, `series.rst`, whatsnew, tests.

Say: "Triage is a human job, and it is free."

---

## Step 2. Turn the request into a spec, by hand (2 min)

Open `spec.md`: 8 numbered items, one obligation each. This is the whole SDD artifact. There is no plan.md, tasks.md or research.md.

Point at why each item exists:
- Items 1-3: the behaviour the requester asked for, plus the error cases.
- Item 4: the NaN and pyarrow complaint, which needs both string storages.
- Items 5-8: the pandas obligations nobody asked for, but that review will demand.

Say: "Writing the spec is cheap for a human and expensive for a model. The model writes code; you write the contract."

---

## Step 3. Price the spec before spending anything (2 min)

```powershell
node ..\tokenforward\scripts\tf-launch.js plan 80k spec.md --dry
node ..\tokenforward\scripts\tf-launch.js plan 150k spec.md --dry
node ..\tokenforward\scripts\tf-launch.js plan 350k spec.md --dry
```

| Budget | Fits | What it means |
|---|---|---|
| 80k | 0 of 8 | A session costs ~34k before any work starts. Too small to do anything. |
| 150k | 3 of 8 | The core method and its errors. Both storages, Index, docs and tests are deferred. |
| 350k | 8 of 8 | The whole request, estimated ~302k for the items. |

Under a second, no tokens, no API.

---

## Step 4. Make the economic decision (1 min)

This is the moment to teach. The developer has a number per item and chooses:

- **Option A, ship it all now:** `/tfd 350k spec.md`. About $0.90 at $3 per million input tokens.
- **Option B, ship the core today and the rest next sprint:** `/tfd 150k spec.md`. The changelog lists the deferred items, which become the next ticket.
- **Option C, push back:** item 4 (two storages) is the single most expensive item. Ask the requester whether object dtype alone is enough for v1.

Say: "Without a price, nobody can make this call. With TokenForward the price exists before the first token."

For the demo, pick Option A so the comparison below is like for like.

---

## Step 5. Implement under the budget, side by side with plain Claude Code (start now, check back at minute ~20)

Left terminal (`pandas-plain`), the usual way:
```powershell
claude --dangerously-skip-permissions
```
```
Implement every item in spec.md.
```

Right terminal (`pandas`), the TokenForward way:
```powershell
claude --dangerously-skip-permissions
```
```
/tfd 350k spec.md
```

(`--dangerously-skip-permissions` only because these are throwaway demo folders, so neither side waits for approvals.)

While both run, narrate the right side:
- The plan table is printed, and the budget is armed. The status line shows `TF [##--------] 70k/350k etok | map`.
- The 8-line spec card: Goal / Interface / Touch / Acceptance / Out of scope.
- `TokenForward: accessor.py has 4885 lines (... paid again on every later turn)`: the whole-file read is blocked, and the model reads a 120-line range instead.
- Tests are written first. The phase moves to `build` on the first edit, then `verify` on the first `python run_tests.py`.

Then scroll the left side and count its whole-file reads.

---

## Step 6. Close the loop with the requester (2 min)

The right side ends with the changelog. Paste it as the reply on the issue:
```
Done: 1-8 | Deferred: none | Files: pandas/core/strings/accessor.py, object_array.py, _arrow_string_mixins.py, ... | Tests: N/N
```
The record, with measured spend next to the planned number:
```powershell
type .tokenforward\CHANGELOG.md
```
Prove it works:
```powershell
python run_tests.py pandas/tests/strings/test_strings.py -k truncate -q
```

---

## Step 7. Show the saving (2 min)

```powershell
node $HOME\tfd-class\tokenforward\scripts\tf-launch.js sessions $HOME\tfd-class\pandas-plain $HOME\tfd-class\pandas
```
This prints each session's turns, effective tokens, raw tokens and USD, and then `NN% fewer effective tokens in the cheaper one`.

Run the tests in `pandas-plain` too, so the room sees both sides did the job.

If the left side is still running, the saving shown is a floor. Its total only grows.

---

## The developer's reflex, to leave on the board

```
Request arrives
  1. Triage with the graph        0 tokens
  2. Write the spec by hand       0 tokens
  3. /tfd-plan <budget> spec.md   0 tokens   price per item
  4. Decide scope with the price  0 tokens   ship / defer / push back
  5. /tfd <budget> spec.md        tokens spent only on code and tests
  6. Changelog -> reply on issue  0 tokens
```

Five of the six steps are free. That is why spec-driven development does not have to be token intensive.

---

## Setup reminder (only if not done)

```powershell
irm https://raw.githubusercontent.com/sayonsom/tokenforward/main/setup.ps1 | iex
cd $HOME\tfd-class\pandas
git worktree add ..\pandas-plain bench-base
Copy-Item run_tests.py, spec.md ..\pandas-plain\
```
