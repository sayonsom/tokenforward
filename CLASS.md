# Token-Optimised Brownfield Development: 30-minute class

Audience: senior engineers, $30/month API credits, already on Spec Kit, saying it burns tokens.
Claim to prove: on a complex brownfield ticket, TokenForward cuts effective tokens by X% vs their Spec Kit workflow, graphify adds Y% on top, with the same hidden acceptance tests passing.
X and Y come from your pre-class run. Do not quote numbers you have not measured.

## The demo task

Repo: httpx @ b5addb64 (~8.8k LOC, `_client.py` = 2,019 lines). Ticket: `bench/tickets/client_retries/TICKET.md`.
First-class client retries: new `httpx.Retry` config, `Client(retries=)` + `AsyncClient(retries=)`, per-request override via extensions, per-hop retry inside the send path (redirects, event hooks), new `RetryError` in the exception hierarchy, `response.extensions["retries"]`, sorted `__all__`, docs page + mkdocs nav.
Why it is a Spec Kit-class ticket: 6 files across config, client (sync + async), exceptions, exports, docs; hidden brownfield conventions (httpx has a test that `__all__` stays sorted).
Scoring: 18 hidden acceptance tests + full existing suite for regressions. Reference solution passes 18/18 with 0 regressions; unmodified httpx fails 18/18.

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
2. Smoke test (cheap): `python bench/run_bench.py --arms tfd-graph --model haiku --skip-regress`
3. Real run (the numbers for the slide):
   ```
   python bench/run_bench.py --arms speckit,tfd-bare,tfd-graph,speckit-tfd --model sonnet --budget 400k
   ```
   Check `total_cost_usd` in the log after the first arm and stop if it is running away. `--runs 3` for medians if you have the budget.
   Output: `bench/results/<stamp>/report.html`. KPI tiles at the top: % fewer effective tokens vs Spec Kit for each TokenForward arm, and graphify's marginal %. Screenshot it.
4. If TokenForward fails acceptance because the budget blocked it, raise `--budget` and rerun. Report the budget you used.
5. Live demo repo: fresh httpx at b5addb64 with `graphify extract . --code-only && graphify claude install`, TokenForward installed, statusline on.

## Run of show

| Min | Segment | On screen |
|---|---|---|
| 0-3 | The bill | Cost = sum over turns of context size. Turn 1 at 20k, turn 40 at 90k. Output is a sliver. |
| 3-7 | Where Spec Kit spends | Spec Kit installs ~19k words of skill instructions. Each phase is a fresh load plus generated docs (spec, plan, tasks) that later phases read back. Show `specs/` from the pre-run: line count vs code lines. |
| 7-10 | graphify | `graphify query "where does the client send a single request and where are exceptions exported"`. Names `_send_single_request`, `_exceptions.py`, `__init__.py` without reading `_client.py`. |
| 10-20 | TokenForward live | `/tfd 400k` + paste the ticket. Narrate: spec card, a denied whole-file read of `_client.py` with the reason, ranged reads, phase flips on first edit and first pytest. You will not finish in 10 minutes; stop at verify and move on. |
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
