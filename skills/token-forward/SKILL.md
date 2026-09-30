---
name: token-forward
description: Use when the user states a token or cost budget for a coding task ("max 100k tokens", "spend at most", "cheap as possible", "low on credits"), wants to implement a spec or Spec Kit tasks cheaply, or asks what fits in a budget. Budget-first spec-driven workflow: plan with the zero-token planner, map cheaply, tests as spec, minimal build, targeted verify, minimal changelog.
---
# Token-forward development

Cost in an agent loop is roughly sum over turns of (context size). Two levers matter most:
fewer turns, smaller context. Output tokens matter less than people think.

0. Plan first, for free: `node "${CLAUDE_PLUGIN_ROOT}/scripts/tf-launch.js" plan <budget> <spec.md>` sizes each spec item against the real code and admits what fits. Implement only admitted items.
1. Commit the budget forward: map 25%, build 45%, verify 20%, reserve 10%.
2. Map without reading. `graphify query "<question>"` if `graphify-out/graph.json` exists, else Grep -n. Read only line ranges (offset/limit, <=120 lines). Every line read is re-paid on every later turn.
3. Spec card in the reply, not in files: Goal / Interface / Touch / Acceptance / Out of scope, 8 lines max.
4. Tests first. The tests are the spec: executable, cheap, and they end the loop.
5. Smallest change that passes. Stdlib and existing helpers first. Follow existing patterns (exports, `__all__` ordering, naming).
6. Verify narrow then broad: `pytest <new_test_file> -q -x`, then `pytest -q` once.
7. Batch parallel tool calls. No narration between calls. Edit, do not rewrite files.
8. At 80%: finish mode. At 100%: stop and report what is left.
9. Final reply is a minimal changelog: Done / Deferred / Files / Tests. The Stop hook appends it, with measured spend, to `.tokenforward/CHANGELOG.md`.
