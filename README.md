# TokenForward

Budget-first agentic development for Claude Code. Say how much you want to spend, up front. The plugin commits that budget to phases, enforces it with hooks, and writes a receipt.

```
/tfd 250k Add a RetryTransport to httpx ...
# or just say it: "Budget: max 250k tokens. Add a RetryTransport ..."
```

## Install

```
/plugin marketplace add <your-github>/tokenforward
/plugin install tokenforward@tokenforward
```
Local dev: `claude --plugin-dir /path/to/tokenforward`

Recommended ecosystem (TokenForward detects both and adapts its instructions):
```
uv tool install graphifyy && graphify extract . --code-only && graphify claude install   # AST graph, 0 LLM tokens
/plugin marketplace add DietrichGebert/ponytail && /plugin install ponytail@ponytail      # minimal-code rules
```

Statusline (optional, recommended for demos), in `~/.claude/settings.json`:
```json
"statusLine": { "type": "command", "command": "python3 /path/to/tokenforward/scripts/tf.py statusline" }
```
Shows `TF [######----] 148k/250k etok 59% ~$0.44 | build`.

## What it does

| Mechanism | Hook | Why it saves tokens |
|---|---|---|
| Budget parse + forward allocation (map 25 / build 45 / verify 20 / reserve 10) | UserPromptSubmit | The agent plans to a number instead of until-done |
| Whole-file read guard (files > 300 lines) | PreToolUse | Every line read is re-paid on every later turn as cached context |
| Re-read guard (same range, unchanged) | PreToolUse | Kills the most common silent waste |
| Map-overrun and 80% finish-mode nudges | PostToolUse | Stops exploration creep |
| Hard stop at 100% | PreToolUse | Budget is a contract |
| Zero-cost phase inference (first Edit = build, first pytest = verify) | PostToolUse | Phase tracking without extra tool calls |
| Receipt `.tokenforward/receipts/<session>.json` | Stop | Proof of spend per task |

Spec-lite: the spec is an 8-line card in the reply plus failing tests. No spec/plan/task files.

## Unit: effective tokens (etok)

`etok = input + 1.25 x cache_write + 0.1 x cache_read + 5 x output`

Input-token equivalents at API prices. Output costs 5x input on current Claude models, so etok is proportional to dollars: `usd = etok x input_price / 1e6`. Set `TF_USD_PER_MTOK_IN` to your model's input price (default 3.0).

Env: `TF_ENFORCE=0` (track only), `TF_BIG_FILE_LINES=300`. `python3 scripts/tf.py off` clears budgets in the current project.

## Benchmark

`bench/` runs Spec Kit (warm) vs TokenForward vs TokenForward + graphify (plus optional Spec Kit + TokenForward, vibe) on a complex httpx ticket with 18 hidden acceptance tests. See `CLASS.md`.
