---
description: Verify complete coverage, integrity, freshness, and GitHub baseline approval
scripts:
  sh: scripts/bash/delivery.sh verify
  ps: scripts/powershell/delivery.ps1 verify
  py: scripts/python/delivery.py verify
---

# Verify complete coverage, integrity, freshness, and GitHub baseline approval

Consider user arguments: `$ARGUMENTS`.
Use the active feature's spec.md, plan.md and tasks.md. Resolve the actual feature and PR numbers;
never guess a reviewer, fabricate evidence, approve as a human, or mark missing checks successful.
Read the installed extension README for command examples and prerequisites.

Invoke the deterministic Python runner from the project root:
`uv run --script .specify/extensions/delivery/scripts/python/delivery.py --feature specs/<feature> verify`
Append the required command arguments. `plan` requires `--mapping <file>`; all other commands require
`--baseline-pr <number>`. `verify`, `status`, and the acceptance gate also use `--pr <number>`.
The gate defaults to acceptance; use `--phase baseline` only before implementation.
