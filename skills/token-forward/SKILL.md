---
name: token-forward
description: Use when the user states a token or cost budget for a coding task ("max 100k tokens", "spend at most", "cheap as possible", "low on credits"), or works in a large brownfield repo on a tight API budget. Budget-first spec-lite workflow: map cheaply, spec as tests, minimal build, targeted verify.
---
# Token-forward development

Cost in an agent loop is roughly sum over turns of (context size). Two levers matter most:
fewer turns, smaller context. Output tokens matter less than people think.

1. Commit the budget forward: map 25%, build 45%, verify 20%, reserve 10%.
2. Map without reading. `graphify query "<question>"` if `graphify-out/graph.json` exists, else Grep -n. Read only line ranges (offset/limit, <=120 lines). Every line read is re-paid on every later turn.
3. Spec card in the reply, not in files: Goal / Interface / Touch / Acceptance / Out of scope, 8 lines max.
4. Tests first. The tests are the spec: executable, cheap, and they end the loop.
5. Smallest change that passes. Stdlib and existing helpers first. Follow existing patterns (exports, `__all__` ordering, naming).
6. Verify narrow then broad: `pytest <new_test_file> -q -x`, then `pytest -q` once.
7. Batch parallel tool calls. No narration between calls. Edit, do not rewrite files.
8. At 80%: finish mode. At 100%: stop and report what is left.
