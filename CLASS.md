# Token-Optimised Brownfield Development: 30-minute class

Audience: senior engineers, $30/month API credits, told to do SDD, pushing back that it wastes tokens.
Thesis: they are right about the verbosity and wrong about the spec. Cost in an agent loop is sum over turns of context size. Cut turns, cut context, keep the spec executable.

## Before class (do tonight / this morning)

1. Push this folder to GitHub (`<you>/tokenforward`) so students can `/plugin marketplace add` it.
2. Run the benchmark once, keep the report on screen. Cheap dry run first:
   ```
   python bench/run_bench.py --arms tfd --model haiku --skip-regress      # smoke test, cents
   python bench/run_bench.py --arms vibe,speckit,tfd --model sonnet       # the real one
   ```
   Or in Docker (clean HOME, no global plugins leaking into the baseline arms): see `Dockerfile` header.
   Output: `bench/results/<stamp>/report.html` + `results.json`. Screenshot both for proof.
3. Local demo repo: `git clone https://github.com/encode/httpx && cd httpx && git checkout b5addb64`
   `graphify extract . --code-only && graphify claude install` (3 s, 0 tokens). Install ponytail + tokenforward. Statusline on.
4. Have a second terminal with `tail -f` nothing; just `cat .tokenforward/receipts/*.json` ready.

## Run of show

| Min | Segment | What you do on screen |
|---|---|---|
| 0-3 | The bill | One slide or whiteboard: turn 1 context 20k, turn 30 context 80k. Cost = area under that curve. Output is a sliver. "Your $30 is a context-size problem." |
| 3-8 | Four leaks in brownfield | 1. Whole-file reads re-paid every turn (httpx `_client.py` = 2,019 lines, ~24k tokens, every turn after). 2. Process verbosity: Spec Kit ships ~19k words of skill instructions plus spec/plan/tasks docs. 3. Turn count: narration, serial tool calls. 4. Code volume: unrequested abstractions. Map each leak to a tool: graphify, TokenForward spec card, batching + budget, ponytail. |
| 8-12 | graphify live | `graphify query "where are transports defined and exported"` on httpx. Point: 3-second AST build, zero LLM tokens, answer names `_transports/__init__.py`, `httpx/__init__.py`, `test_exported_members.py` without reading a file. |
| 12-22 | TokenForward live | In httpx: `/tfd 250k` + paste `bench/TICKET.md`. Narrate the statusline. Expect: spec card (8 lines), a denied whole-file read with the reason visible, phase flip map -> build on first edit, build -> verify on first pytest, receipt at the end. If it goes long, let it run and move on. |
| 22-27 | The benchmark | Open `report.html`. Same ticket, same model, hidden acceptance tests. Read three numbers: cost, turns, acceptance. Point at the regressions column: httpx has a test that `__all__` stays sorted; brownfield punishes agents that do not look at conventions. |
| 27-30 | Adoption | Install lines on screen. One rule to take home: "State the budget before the task. Make the spec a failing test." |

## Talking points for pushback

- "SDD is overkill": keep the discipline, drop the documents. The card is 8 lines; the tests are the spec and they terminate the loop.
- "Budgets make the agent stop early": the reserve is 10%, finish mode starts at 80%, and the receipt tells you whether the budget or the task was wrong. Tune once per repo.
- "Graphs go stale": `graphify hook install` rebuilds on commit, AST only, no cost.
- "n=1": correct. Say it first. `--runs 3` for medians; ponytail's own benchmark is the precedent for publishing flops too.

## Fallbacks

- No network / API trouble: show the pre-run report and the receipt JSON.
- Hook not firing: `claude --debug` shows hook execution; `python3 scripts/tf.py status` in the repo shows state.
- Budget blocks too early: `python3 scripts/tf.py off`, rerun with a larger number.

## Student hands-on (if time, or as homework)

```
/plugin marketplace add <you>/tokenforward
/plugin install tokenforward@tokenforward
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
uv tool install graphifyy && graphify extract . --code-only && graphify claude install
```
Then on their own repo: `/tfd 150k <a ticket from their backlog>` and share the receipt.
