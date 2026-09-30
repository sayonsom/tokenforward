# TokenForward

Spec-driven development under a token budget, for Claude Code. Give it a spec and a number. It plans what fits (locally, zero tokens), implements only that, enforces the budget with hooks, and hands back a minimal changelog.

```
/tfd-plan 150k specs/012-average-where/tasks.md            # what fits? zero tokens, no changes
/tfd 150k specs/012-average-where/tasks.md                 # implement what fits, return a changelog
/tfd 150k specs/012-average-where/spec.md --since main     # only the spec lines changed since main
/tfd 80k "Add a --json flag to the export command ..."     # inline spec works too
```

Works with Spec Kit specs (`spec.md` FR-### items, `tasks.md` T### items) or any markdown with numbered or bulleted items.

## Install

Requirements: Claude Code, Node (runs the hooks on every OS), Python 3.9+, git. On Windows, Git for Windows (Claude Code needs it anyway).

```
/plugin marketplace add <your-github>/tokenforward
/plugin install tokenforward@tokenforward
```
Local: `claude --plugin-dir /path/to/tokenforward` (on Windows, `C:/path/to/tokenforward`).

Recommended ecosystem (detected automatically):
```
uv tool install graphifyy
graphify extract <repo path> --code-only     # AST graph, 0 LLM tokens; planner and agent both use it
graphify claude install                      # run inside the repo
/plugin marketplace add DietrichGebert/ponytail  then  /plugin install ponytail@ponytail
```

Statusline (recommended for demos), in `~/.claude/settings.json`:
```json
"statusLine": { "type": "command", "command": "node /path/to/tokenforward/scripts/tf-launch.js statusline" }
```
Shows `TF [######----] 148k/250k etok 59% ~$0.44 | build`.

## How it works

| Piece | Where | What it does |
|---|---|---|
| Planner | `tf-launch.js plan` (local Python, 0 tokens) | Splits the spec into items, locates the code each touches (graphify graph, else git grep), sizes the reads from real line counts, simulates the agent loop turn by turn, admits items in order until 90% of the budget |
| Calibration | `.tokenforward/calibration.json` | After each run, actual / planned is recorded; the planner multiplies by the median of the last 5. Uncalibrated estimates are +-40% |
| Budget arming | PostToolUse (after the plan command) or UserPromptSubmit ("budget: max 100k tokens") | Injects the protocol and the admitted item list |
| Whole-file read guard (> 300 lines) | PreToolUse | Every line read is re-paid on every later turn as cached context |
| Re-read guard | PreToolUse | Same range, unchanged since, is denied once |
| Map-overrun and 80% nudges, hard stop at 100% | PostToolUse / PreToolUse | Stops exploration creep; budget is a contract |
| Phase inference | PostToolUse | First edit = build, first test run = verify. No extra tool calls |
| Changelog + receipt | Stop | Appends the agent's Done / Deferred / Files / Tests reply plus measured spend and `git diff --stat` to `.tokenforward/CHANGELOG.md`; receipt JSON in `.tokenforward/receipts/` |

Terminal use without Claude: `node scripts/tf-launch.js plan 150k specs/012/tasks.md --dry`.

## Unit: effective tokens (etok)

`etok = input + 1.25 x cache_write + 0.1 x cache_read + 5 x output`

Input-token equivalents at API prices. Output costs 5x input on current Claude models, so etok is proportional to dollars: `usd = etok x input_price / 1e6`. Set `TF_USD_PER_MTOK_IN` to your model's input price (default 3.0).

Env: `TF_ENFORCE=0` (track only), `TF_BIG_FILE_LINES=300`, `TF_PYTHON` (force an interpreter). `node scripts/tf-launch.js off` clears budgets in the current project.

## Benchmark

`bench/` runs Spec Kit (warm) vs TokenForward vs TokenForward + graphify (plus Spec Kit + TokenForward, and vibe) on a real numpy feature (`where=` for `np.average`, 18 hidden acceptance tests; numpy is tested against the prebuilt wheel, no compile) or two httpx tickets. See `CLASS.md`.
