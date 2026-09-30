---
description: What fits in this budget? Sizes each spec item against the code, zero tokens, no changes.
argument-hint: <budget e.g. 150k> <spec.md | tasks.md> [--since <git ref>]
---
Run exactly this and show its output verbatim, then stop. Do not read files or implement anything:
`node "${CLAUDE_PLUGIN_ROOT}/scripts/tf-launch.js" plan $ARGUMENTS --dry`
