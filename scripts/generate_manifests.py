"""Generate extension commands from a small, reviewed command registry."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTIONS = {
    "plan": "Map all obligations to demonstrations and prepare the baseline for human approval",
    "demo": "Execute approved scenarios and capture assertion evidence",
    "verify": "Verify complete coverage, integrity, freshness, and GitHub baseline approval",
    "present": "Generate L0, L1, L2 browser and editable PowerPoint decks",
    "status": "Report missing evidence, failures, and approval state",
    "gate": "Fail closed until baseline approval or final human acceptance is verified",
}
for command, description in DESCRIPTIONS.items():
    frontmatter = {
        "description": description,
        "scripts": {
            "sh": f"scripts/bash/delivery.sh {command}",
            "ps": f"scripts/powershell/delivery.ps1 {command}",
            "py": f"scripts/python/delivery.py {command}",
        },
    }
    body = f"""# {description}

Consider user arguments: `$ARGUMENTS`.
Use the active feature's spec.md, plan.md and tasks.md. Resolve the actual feature and PR numbers;
never guess a reviewer, fabricate evidence, approve as a human, or mark missing checks successful.
Read the installed extension README for command examples and prerequisites.

Invoke the deterministic Python runner from the project root:
`uv run --script .specify/extensions/delivery/scripts/python/delivery.py --feature specs/<feature> {command}`
Append the required command arguments. `plan` requires `--mapping <file>`; all other commands require
`--baseline-pr <number>`. `verify`, `status`, and the acceptance gate also use `--pr <number>`.
The gate defaults to acceptance; use `--phase baseline` only before implementation.

"""
    if command == "plan":
        body += """Create delivery/mapping.yml from the predefined specification, plan, and every task.
Use examples/mapping.yml as the schema guide. Give every requirement and acceptance criterion an
explicit ID and source, preserving original meaning. Map every T-number exactly once as an obligation.
Specify executable scenarios with outcome assertions, including failures and regression checks.
UI: observable text/visibility assertions plus captured trace. API: content and state assertions.
CLI: expected exit and output. Noninteractive tasks: explicit inspection assertions.
Include narrative context for all audiences; label expected benefits as expectations.
Run the plan command, open a planning PR, and ask the human to review the printed baseline digest.
Use a separate frozen planning PR so later implementation pushes do not dismiss its approval.
Do not implement until the baseline gate passes. Keep all baseline revisions and scope differences.
"""
    if command == "demo":
        body += """Run all approved scenarios. On failure, preserve evidence, make only in-scope fixes,
and rerun using --repair-of <latest-run-id>. At most three repair cycles are allowed.
Run all scenarios again, including regression checks, after each repair. Never weaken expectations.
If environment access, dependencies, or approvals are missing, report BLOCKED with the concrete cause.
"""
    if command == "present":
        body += """Export both formats for all three levels using the same content source. Render and
inspect slide layouts, links, speaker notes, and text editability. Include the live-demo runbook and
captured fallback evidence. Do not hide failed, deferred, or unmeasured work.
"""
    if command == "gate":
        body += """A nonzero exit stops progression. Missing protection support or unavailable GitHub
access is a blocker, never permission to downgrade enforcement. Do not merge or deploy automatically.
"""
    (ROOT / "commands" / f"speckit.delivery.{command}.md").write_text(
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + body.rstrip() + "\n"
    )
manifest = {
    "schema_version": "1.0",
    "extension": {
        "id": "delivery",
        "name": "Spec Kit Delivery",
        "version": "0.1.0",
        "description": "Demonstrate, verify, and present deliveries with human acceptance.",
        "author": "bbjwz",
        "repository": "https://github.com/bbjwz/spec-kit-delivery",
        "license": "MIT",
        "category": "process",
        "effect": "read-write",
    },
    "requires": {
        "speckit_version": "==1.0.12",
        "tools": [{"name": name, "required": True} for name in ("uv", "node", "npm", "gh")],
        "commands": ["speckit.tasks", "speckit.implement"],
    },
    "provides": {
        "commands": [
            {
                "name": f"speckit.delivery.{name}",
                "file": f"commands/speckit.delivery.{name}.md",
                "description": description,
            }
            for name, description in DESCRIPTIONS.items()
        ]
    },
    "hooks": {
        "after_tasks": {"command": "speckit.delivery.plan", "optional": False, "priority": 30},
        "before_implement": {
            "command": "speckit.delivery.gate",
            "optional": False,
            "priority": 1,
            "description": "Invoke gate with --phase baseline before implementation",
        },
        "after_implement": [
            {"command": f"speckit.delivery.{name}", "optional": False, "priority": priority}
            for name, priority in (("demo", 20), ("present", 30), ("verify", 40))
        ],
    },
}
(ROOT / "extension.yml").write_text(yaml.safe_dump(manifest, sort_keys=False))
