---
description: Spec-driven development under a token budget. Plans what fits (0 tokens), implements only that, returns a minimal changelog.
argument-hint: <budget e.g. 200k> <spec.md | tasks.md | inline spec> [--since <git ref>]
---
Arguments: $ARGUMENTS

1. If the spec is inline text rather than a file path, write it verbatim to `.tokenforward/spec.md` and use that path.
2. Before anything else, run exactly once:
   `node "${CLAUDE_PLUGIN_ROOT}/scripts/tf-launch.js" plan <budget> <spec path> [--since <ref>]`
   It sizes every spec item against the code (locally, zero tokens), admits the items that fit the budget, and arms the budget.
3. Follow the TokenForward protocol injected after that command. Implement only the admitted items, in order.
4. Final reply is the changelog in the protocol format. Nothing else.
