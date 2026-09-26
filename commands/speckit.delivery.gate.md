---
description: Fail closed until baseline approval or final human acceptance is verified
scripts:
  sh: scripts/bash/delivery.sh gate
  ps: scripts/powershell/delivery.ps1 gate
  py: scripts/python/delivery.py gate
---

# Fail closed until baseline approval or final human acceptance is verified

Consider user arguments: `$ARGUMENTS`.
Use the active feature's spec.md, plan.md and tasks.md. Resolve the actual feature and PR numbers;
never guess a reviewer, fabricate evidence, approve as a human, or mark missing checks successful.
Read the installed extension README for command examples and prerequisites.

Invoke the deterministic Python runner from the project root:
`uv run --script .specify/extensions/delivery/scripts/python/delivery.py --feature specs/<feature> gate`
Append the required command arguments. `plan` requires `--mapping <file>`; all other commands require
`--baseline-pr <number>`. `verify`, `status`, and the acceptance gate also use `--pr <number>`.
The gate defaults to acceptance; use `--phase baseline` only before implementation.

A nonzero exit stops progression. Missing protection support or unavailable GitHub
access is a blocker, never permission to downgrade enforcement. Do not merge or deploy automatically.
