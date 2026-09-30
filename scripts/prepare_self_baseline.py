"""Prepare real project obligations; never manufacture approval or passing evidence."""

from pathlib import Path

import yaml
from speckit_delivery.core import make_plan

ROOT = Path(__file__).resolve().parents[1]
FEATURE = ROOT / "specs/001-delivery-v1"
obligations = []
for source, prefix, kind in [("spec.md", "FR-", "requirement"), ("spec.md", "AC-", "acceptance")]:
    for line in (FEATURE / source).read_text().splitlines():
        if line.startswith("- " + prefix):
            identifier, text = line[2:].split(": ", 1)
            obligations.append({"id": identifier, "kind": kind, "text": text, "source": source})
for line in (FEATURE / "tasks.md").read_text().splitlines():
    if line.startswith("- ["):
        identifier, text = line[6:].split(" ", 1)
        obligations.append({"id": identifier, "kind": "task", "text": text, "source": "tasks.md"})
all_ids = [o["id"] for o in obligations]
verification_ids = [i for i in all_ids if i != "T007"]
mapping = {
    "title": "Spec Kit Delivery v1",
    "obligations": obligations,
    "scenarios": [
        {
            "id": "regression",
            "title": "Delivery regression suite",
            "kind": "cli",
            "regression": True,
            "obligations": verification_ids,
            "expected": "All unit and execution integration tests pass.",
            "command": ["uv", "run", "--locked", "--extra", "test", "pytest", "-q"],
            "timeout_seconds": 300,
            "assertions": [
                {"field": "exit_code", "value": 0},
                {"field": "stdout", "operator": "contains", "value": "passed"},
            ],
        },
        {
            "id": "install",
            "title": "Clean Spec Kit installation",
            "kind": "cli",
            "obligations": ["FR-006", "AC-005", "T006"],
            "expected": "All commands, preset and workflow install in a clean project.",
            "command": ["bash", "scripts/verify_install.sh"],
            "timeout_seconds": 300,
            "assertions": [
                {"field": "exit_code", "value": 0},
                {"field": "stdout", "operator": "contains", "value": "speckit-delivery-install: PASS"},
            ],
        },
        {
            "id": "honest-status",
            "title": "Incomplete acceptance remains visible",
            "kind": "inspection",
            "obligations": ["T007", "AC-006"],
            "expected": "The report documents that live human acceptance is pending.",
            "file": "docs/validation.md",
            "assertions": [{"field": "text", "operator": "contains", "value": "Human acceptance: PENDING"}],
        },
    ],
    "narrative": {
        "problem": "Agents can claim completion without demonstrating the agreed work.",
        "expected_benefit": "Expected to improve review discipline; business benefit is not measured.",
        "implementation": "Baseline mapping, execution evidence, shared deck content, and GitHub approval gates.",
        "operations": "Use synthetic data, preserve failures, and require trusted CI and human acceptance.",
        "limitations": [
            "Real acceptance remains pending; local fixtures do not prove human sign-off.",
            "Private repository protection requires an eligible GitHub plan.",
        ],
    },
}
(FEATURE / "delivery").mkdir(exist_ok=True)
path = FEATURE / "delivery/mapping.yml"
path.write_text(yaml.safe_dump(mapping, sort_keys=False))
print(make_plan(ROOT, FEATURE, path))
