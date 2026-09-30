# Token-Optimised Brownfield Development: 30-minute class

Audience: senior engineers, $30/month API credits, already on Spec Kit, saying it burns tokens.
Claim to prove: on a real numpy feature, TokenForward cuts effective tokens by X% vs their Spec Kit workflow, graphify adds Y% on top, with the same hidden acceptance tests passing.
X and Y come from your pre-class run. Do not quote numbers you have not measured.

## The demo task

Repo: numpy v2.4.6 (~272k Python + ~384k C LOC). Ticket: `bench/tickets/numpy_average_where/TICKET.md`.
Add `where=` to `np.average` and `np.ma.average`, matching `np.mean(where=)`: weights, `returned`, `keepdims`, axis tuples, broadcasting, empty slices, masked arrays.
It is a real gap (`np.mean` has `where=`, `np.average` does not) and pure Python, so no C build.
Why it is a Spec Kit-class ticket: the implementation sits in `_function_base_impl.py` (5,760 lines) and its tests in `test_function_base.py` (4,756 lines). The numpy conventions a newcomer misses are all checked:
- the `__array_function__` dispatcher must pass `where`
- all 26 `average` overloads in the `.pyi` stubs must accept `where`
- `versionadded` in both docstrings
- a towncrier release-note fragment

How it runs without compiling numpy: the checkout gets a `run_tests.sh` (same for every arm) that overlays changed `.py`/`.pyi` files onto a prebuilt numpy 2.4.6 wheel. numpy's own suites for the touched modules run in about 6 s.
Scoring: 18 hidden acceptance tests plus `test_function_base.py` and `ma/tests/test_extras.py` for regressions. The reference solution passes 18/18 with 0 regressions; unmodified numpy passes 1/18.
graphify builds a 26.6k-node graph of numpy in about 25 s from the AST, using no LLM tokens.

Backup tickets on httpx: `--ticket client_retries` (complex, 18 tests), `--ticket retry_transport` (small, 9 tests).

## Arms

| Arm | What it is | Why it is in the room |
|---|---|---|
| `speckit` | Spec Kit, warm: constitution already written (cost excluded), then specify, plan, tasks, implement | Their current workflow. The 100% baseline |
| `tfd-bare` | TokenForward alone | Isolates the plugin |
| `tfd-graph` | TokenForward + graphify (AST graph, 3 s, 0 tokens) | The headline |
| `speckit-tfd` | Spec Kit with TokenForward + graphify loaded | "Keep your process, cut the spend" |
| `vibe` | One prompt | Optional floor reference |

Ponytail: `--with-ponytail` adds it to the TokenForward arms. Keep it off for the headline so the percentage belongs to TokenForward and graphify alone; run it as a second report if time allows.

## Before class

1. Push this folder to GitHub (`<you>/tokenforward`).
2. Python env for scoring: `uv venv ~/npbench && VIRTUAL_ENV=~/npbench uv pip install numpy==2.4.6 pytest hypothesis`, then pass `--python ~/npbench/bin/python` (the harness checks the version).
3. Smoke test (cheap): `python bench/run_bench.py --arms tfd-graph --model haiku --skip-regress --python ~/npbench/bin/python`
4. Real run (the numbers for the slide):
   ```
   python bench/run_bench.py --ticket numpy_average_where --arms speckit,tfd-bare,tfd-graph,speckit-tfd \
     --model sonnet --budget 400k --python ~/npbench/bin/python
   ```
   Check `total_cost_usd` in the log after the first arm and stop if it is running away. `--runs 3` for medians if you have the budget.
   Output: `bench/results/<stamp>/report.html`. KPI tiles at the top: % fewer effective tokens vs Spec Kit for each TokenForward arm, and graphify's marginal %. Screenshot it.
5. If TokenForward fails acceptance because the budget blocked it, raise `--budget` and rerun. Report the budget you used.
6. Live demo repo: copy `bench/work/base-numpy` (it already has `run_tests.sh`), run `graphify extract <path> --code-only` from outside the folder (numpy's source tree shadows the installed numpy), then `graphify claude install` inside it. TokenForward installed, statusline on.

## Run of show

| Min | Segment | On screen |
|---|---|---|
| 0-3 | The bill | Cost = sum over turns of context size. Turn 1 at 20k, turn 40 at 90k. Output is a sliver. |
| 3-7 | Where Spec Kit spends | Spec Kit installs ~19k words of skill instructions. Each phase is a fresh load plus generated docs (spec, plan, tasks) that later phases read back. Show `specs/` from the pre-run: line count vs code lines. |
| 7-10 | graphify | `graphify query "where is np.average implemented, dispatched and stubbed"`. Returns `average()` in `_function_base_impl.py` L440, its test module and `array_function_dispatch`, without reading a 5,760-line file. |
| 10-20 | TokenForward live | `/tfd 400k` + paste the ticket. Narrate: spec card, a denied whole-file read of `_function_base_impl.py` with the reason, ranged reads around L434-600, phase flips on first edit and first `./run_tests.sh`. Stop at verify and move on. |
| 20-26 | The numbers | Open `report.html`. Read the tiles: X% vs Spec Kit, Y% from graphify, acceptance per arm, regressions column. Then `speckit-tfd`: they keep Spec Kit and still save. |
| 26-30 | Adoption | Install lines. One rule: state the budget before the task; make the spec a failing test. |

## Pushback answers

- "Different arms got lucky": same ticket, same model, same hidden tests. n=1 is noted on the report; run `--runs 3`.
- "You excluded Spec Kit's setup": yes, deliberately, in its favour. Their constitution already exists.
- "Budget made it stop early": acceptance column shows it. If it failed, the report shows that too.
- "Graph goes stale": `graphify hook install` rebuilds on commit, AST only.

## Fallbacks

- Live run slow or API trouble: show the pre-run report and one arm's receipt (`bench/work/tfd-graph-r0/.tokenforward/receipts/*.json`).
- Hook not firing: `claude --debug`; `python3 scripts/tf.py status` in the repo.
- Smaller ticket for a fully live A/B: `--ticket retry_transport` (9 acceptance tests, single new file).

## Student hands-on

```
/plugin marketplace add <you>/tokenforward
/plugin install tokenforward@tokenforward
uv tool install graphifyy && graphify extract . --code-only && graphify claude install
```
Then `/tfd 150k <a real ticket from their backlog>` and share the receipt.
