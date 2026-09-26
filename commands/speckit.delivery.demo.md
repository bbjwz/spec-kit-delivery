---
description: Execute approved scenarios and capture assertion evidence
scripts:
  sh: scripts/bash/delivery.sh demo
  ps: scripts/powershell/delivery.ps1 demo
  py: scripts/python/delivery.py demo
---

# Execute approved scenarios and capture assertion evidence

Consider user arguments: `$ARGUMENTS`.
Use the active feature's spec.md, plan.md and tasks.md. Resolve the actual feature and PR numbers;
never guess a reviewer, fabricate evidence, approve as a human, or mark missing checks successful.
Read the installed extension README for command examples and prerequisites.

Invoke the deterministic Python runner from the project root:
`uv run --script .specify/extensions/delivery/scripts/python/delivery.py --feature specs/<feature> demo`
Append the required command arguments. `plan` requires `--mapping <file>`; all other commands require
`--baseline-pr <number>`. `verify`, `status`, and the acceptance gate also use `--pr <number>`.
The gate defaults to acceptance; use `--phase baseline` only before implementation.

Run all approved scenarios. On failure, preserve evidence, make only in-scope fixes,
and rerun using --repair-of <latest-run-id>. At most three repair cycles are allowed.
Run all scenarios again, including regression checks, after each repair. Never weaken expectations.
If environment access, dependencies, or approvals are missing, report BLOCKED with the concrete cause.
