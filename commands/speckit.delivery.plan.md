---
description: Map all obligations to demonstrations and prepare the baseline for human
  approval
scripts:
  sh: scripts/bash/delivery.sh plan
  ps: scripts/powershell/delivery.ps1 plan
  py: scripts/python/delivery.py plan
---

# Map all obligations to demonstrations and prepare the baseline for human approval

Consider user arguments: `$ARGUMENTS`.
Use the active feature's spec.md, plan.md and tasks.md. Resolve the actual feature and PR numbers;
never guess a reviewer, fabricate evidence, approve as a human, or mark missing checks successful.
Read the installed extension README for command examples and prerequisites.

Invoke the deterministic Python runner from the project root:
`uv run --script .specify/extensions/delivery/scripts/python/delivery.py --feature specs/<feature> plan`
Append the required command arguments. `plan` requires `--mapping <file>`; all other commands require
`--baseline-pr <number>`. `verify`, `status`, and the acceptance gate also use `--pr <number>`.
The gate defaults to acceptance; use `--phase baseline` only before implementation.

Create delivery/mapping.yml from the predefined specification, plan, and every task.
Use examples/mapping.yml as the schema guide. Give every requirement and acceptance criterion an
explicit ID and source, preserving original meaning. Map every T-number exactly once as an obligation.
Specify executable scenarios with outcome assertions, including failures and regression checks.
UI: observable text/visibility assertions plus captured trace. API: content and state assertions.
CLI: expected exit and output. Noninteractive tasks: explicit inspection assertions.
Include narrative context for all audiences; label expected benefits as expectations.
Run the plan command, open a planning PR, and ask the human to review the printed baseline digest.
Use a separate frozen planning PR so later implementation pushes do not dismiss its approval.
Do not implement until the baseline gate passes. Keep all baseline revisions and scope differences.
