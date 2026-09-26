---
description: Generate L0, L1, L2 browser and editable PowerPoint decks
scripts:
  sh: scripts/bash/delivery.sh present
  ps: scripts/powershell/delivery.ps1 present
  py: scripts/python/delivery.py present
---

# Generate L0, L1, L2 browser and editable PowerPoint decks

Consider user arguments: `$ARGUMENTS`.
Use the active feature's spec.md, plan.md and tasks.md. Resolve the actual feature and PR numbers;
never guess a reviewer, fabricate evidence, approve as a human, or mark missing checks successful.
Read the installed extension README for command examples and prerequisites.

Invoke the deterministic Python runner from the project root:
`uv run --script .specify/extensions/delivery/scripts/python/delivery.py --feature specs/<feature> present`
Append the required command arguments. `plan` requires `--mapping <file>`; all other commands require
`--baseline-pr <number>`. `verify`, `status`, and the acceptance gate also use `--pr <number>`.
The gate defaults to acceptance; use `--phase baseline` only before implementation.

Export both formats for all three levels using the same content source. Render and
inspect slide layouts, links, speaker notes, and text editability. Include the live-demo runbook and
captured fallback evidence. Do not hide failed, deferred, or unmeasured work.
