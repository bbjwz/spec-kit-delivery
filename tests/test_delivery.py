from __future__ import annotations

import copy
import sys

import pytest
from speckit_delivery.adapters import assert_values, execute
from speckit_delivery.core import load_baseline, make_plan, run_demo, verify
from speckit_delivery.models import Assertion, Baseline, Scenario
from speckit_delivery.storage import digest, read, source_manifest, write


def test_execution_and_missing_decks(project, authority):
    root, feature = project
    run = run_demo(root, feature, 1, github=authority)
    assert run["status"] == "READY_FOR_REVIEW"
    report = verify(root, feature, 1, github=authority)
    assert report["status"] == "BLOCKED"
    assert any("presentation" in e for e in report["errors"])
    report = verify(root, feature, 1, github=authority, require_presentations=False)
    assert report["status"] == "READY_FOR_REVIEW"
    assert report["acceptance"] is None


def test_real_approval_missing_never_runs(project):
    root, feature = project
    with pytest.raises(ValueError):
        run_demo(root, feature, 1)
    assert not (feature / "delivery/runs/latest.json").exists()


def test_checkbox_is_progress_not_scope(project, authority):
    root, feature = project
    run_demo(root, feature, 1, github=authority)
    (feature / "tasks.md").write_text("- [X] T001 Implement greeting\n")
    assert verify(root, feature, 1, github=authority, require_presentations=False)["status"] == "READY_FOR_REVIEW"
    (feature / "tasks.md").write_text("- [X] T001 Skip greeting\n")
    with pytest.raises(ValueError, match="changed"):
        load_baseline(feature)


@pytest.mark.parametrize("mutation", ["modified", "untracked", "deleted"])
def test_source_changes_invalidate(project, authority, mutation):
    root, feature = project
    run_demo(root, feature, 1, github=authority)
    if mutation == "modified":
        (root / "greet.py").write_text("print('different')\n")
    elif mutation == "untracked":
        (root / "extra.py").write_text("# new source")
    else:
        (root / "greet.py").unlink()
    report = verify(root, feature, 1, github=authority, require_presentations=False)
    assert report["status"] == "BLOCKED"
    assert any("stale" in e for e in report["errors"])


def test_artifact_tampering(project, authority):
    root, feature = project
    run = run_demo(root, feature, 1, github=authority)
    result = feature / f"delivery/runs/{run['run_id']}/greet/result.json"
    result.write_text('{"changed":true}')
    report = verify(root, feature, 1, github=authority, require_presentations=False)
    assert report["status"] == "BLOCKED"
    assert any("altered" in e for e in report["errors"])


def test_duplicate_missing_results(project, authority):
    root, feature = project
    run = run_demo(root, feature, 1, github=authority)
    path = feature / f"delivery/runs/{run['run_id']}/run.json"
    run["records"].append(copy.deepcopy(run["records"][0]))
    write(path, run)
    assert verify(root, feature, 1, github=authority, require_presentations=False)["status"] == "BLOCKED"
    run["records"] = []
    write(path, run)
    assert verify(root, feature, 1, github=authority, require_presentations=False)["status"] == "BLOCKED"


def test_missing_and_duplicate_obligations(project):
    root, feature = project
    raw = read(feature / "delivery/baseline.json")
    raw["obligations"].append(copy.deepcopy(raw["obligations"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        Baseline.model_validate(raw)
    raw = read(feature / "delivery/baseline.json")
    raw["scenarios"][0]["obligations"] = ["T001"]
    with pytest.raises(ValueError, match="coverage"):
        Baseline.model_validate(raw)


def test_task_omission_and_revised_history(project):
    root, feature = project
    old = read(feature / "delivery/baseline.json")
    (feature / "tasks.md").write_text("- [ ] T001 Implement greeting\n- [ ] T002 Document\n")
    with pytest.raises(ValueError, match="every tasks"):
        make_plan(root, feature, root / "mapping.json")
    raw = read(root / "mapping.json")
    raw["obligations"].append({"id": "T002", "kind": "task", "text": "Document", "source": "tasks.md"})
    raw["scenarios"][0]["obligations"].append("T002")
    write(root / "mapping.json", raw)
    make_plan(root, feature, root / "mapping.json")
    assert read(feature / f"delivery/baselines/{digest(old)}.json") == old


def test_failed_attempts_and_three_repair_limit(project, authority):
    root, feature = project
    (root / "greet.py").write_text("print('broken')\n")
    run = run_demo(root, feature, 1, github=authority)
    assert run["status"] == "BLOCKED"
    for cycle in range(1, 4):
        run = run_demo(root, feature, 1, repair_of=run["run_id"], github=authority)
        assert run["repair_cycle"] == cycle
    with pytest.raises(ValueError, match="exhausted"):
        run_demo(root, feature, 1, repair_of=run["run_id"], github=authority)
    assert len(list((feature / "delivery/runs").glob("*/run.json"))) == 4


def test_symlinks_rejected(project, authority):
    root, feature = project
    (root / "link.py").symlink_to(root / "greet.py")
    with pytest.raises(ValueError, match="symlink"):
        source_manifest(root)


def test_api_assertion_and_negative_case(server, tmp_path):
    scenario = Scenario(
        id="api",
        title="API",
        kind="api",
        obligations=["T001"],
        expected="Returns hello",
        url=server + "/api",
        assertions=[
            Assertion(field="status", value=200),
            Assertion(field="json.message", value="hello"),
        ],
    )
    observed, checks = execute(scenario, tmp_path, tmp_path)
    assert all(c["passed"] for c in checks)
    assert not assert_values(observed, [Assertion(field="json.count", value=2)])[0]["passed"]
    assert not assert_values(observed, [Assertion(field="json.missing", value=None)])[0]["passed"]


def test_browser_success_failure_and_captures(server, tmp_path):
    scenario = Scenario.model_validate(
        {
            "id": "ui",
            "title": "UI",
            "kind": "ui",
            "obligations": ["T001"],
            "expected": "Saving is visible",
            "timeout_seconds": 1,
            "steps": [
                {"action": "goto", "target": server},
                {"action": "click", "target": "button"},
                {"action": "assert_text", "target": "button", "value": "Saved"},
            ],
        }
    )
    _, checks = execute(scenario, tmp_path, tmp_path)
    assert all(c["passed"] for c in checks)
    assert (tmp_path / "trace.zip").is_file()
    assert (tmp_path / "screenshot.png").is_file()
    scenario.steps[-1].value = "Wrong"
    _, checks = execute(scenario, tmp_path, tmp_path)
    assert not all(c["passed"] for c in checks)


def test_timeout_and_inspection(tmp_path):
    scenario = Scenario(
        id="cli",
        title="Timeout",
        kind="cli",
        obligations=["T001"],
        expected="Stops",
        timeout_seconds=1,
        command=[sys.executable, "-c", "import time; time.sleep(10)"],
        assertions=[Assertion(field="exit_code", value=0)],
    )
    observed, checks = execute(scenario, tmp_path, tmp_path)
    assert observed["timeout"] and not checks[0]["passed"]
    (tmp_path / "readme.md").write_text("Install the package")
    inspection = Scenario(
        id="doc",
        title="Docs",
        kind="inspection",
        obligations=["T001"],
        expected="Explains installation",
        file="readme.md",
        assertions=[Assertion(field="text", operator="contains", value="Install")],
    )
    assert execute(inspection, tmp_path, tmp_path)[1][0]["passed"]


def test_changed_baseline_review_invalidates_evidence(project, authority):
    root, feature = project
    run_demo(root, feature, 1, github=authority)
    original = authority.baseline_approval
    authority.baseline_approval = lambda *args: dict(original(*args), review_id=2)
    report = verify(root, feature, 1, github=authority, require_presentations=False)
    assert report["status"] == "BLOCKED"
    assert any("approval changed" in reason for reason in report["errors"])
