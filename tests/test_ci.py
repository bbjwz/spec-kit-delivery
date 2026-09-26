from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml
from speckit_delivery.ci import JobReceipt, extract_evidence


def test_receipt_bound_to_feature_baseline_and_pr():
    receipt = JobReceipt(
        {"baseline_pr": 4, "baseline_hash": "abc", "feature": "specs/001-x", "approval": {"review_id": 5}}
    )
    assert receipt.baseline_approval(4, "specs/001-x/delivery/baseline.json", "abc")["review_id"] == 5
    with pytest.raises(ValueError):
        receipt.baseline_approval(4, "specs/002-other/delivery/baseline.json", "abc")
    with pytest.raises(ValueError):
        receipt.baseline_approval(4, "specs/001-x/delivery/baseline.json", "changed")


@pytest.mark.parametrize("name", ["../outside", "/absolute", "baseline.json", "runs/../../outside"])
def test_archive_traversal_and_source_replacement_rejected(tmp_path, name):
    archive = tmp_path / "artifact.zip"
    with ZipFile(archive, "w") as handle:
        handle.writestr(name, "untrusted")
    with pytest.raises(ValueError):
        extract_evidence(archive, tmp_path / "out")


def test_trusted_audit_never_runs_from_review_merge_ref():
    root = Path(__file__).resolve().parents[1]
    # BaseLoader avoids YAML 1.1 treating the GitHub key "on" as a boolean.
    audit = yaml.load((root / ".github/workflows/delivery-acceptance.yml").read_text(), Loader=yaml.BaseLoader)
    assert "pull_request_review" not in audit["on"]
    assert set(audit["on"]) == {"pull_request_target", "workflow_run"}
    assert audit["jobs"]["audit"]["environment"] == "delivery-audit"
    signal = yaml.load((root / ".github/workflows/delivery-review-signal.yml").read_text(), Loader=yaml.BaseLoader)
    assert signal["permissions"] == {}
    assert "secrets." not in str(signal)


def test_isolated_execution_receipt_and_export(project):
    from speckit_delivery.ci import execute_job
    from speckit_delivery.storage import digest, git, read

    root, feature = project
    receipt = {
        "head": git(root, "rev-parse", "HEAD"),
        "feature": str(feature.relative_to(root)),
        "baseline_pr": 1,
        "baseline_hash": digest(read(feature / "delivery/baseline.json")),
        "approval": {"review_id": 1, "reviewer": "fixture"},
    }
    report = execute_job(root, receipt)
    assert report["status"] == "READY_FOR_REVIEW"
    assert len(report["evidence_hash"]) == 64
    receipt["head"] = "wrong"
    with pytest.raises(ValueError, match="checkout"):
        execute_job(root, receipt)


def test_archive_existing_symlink_rejected(tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    destination = tmp_path / "project/specs/feature/delivery"
    destination.mkdir(parents=True)
    (destination / "runs").symlink_to(target)
    archive = tmp_path / "evidence.zip"
    with ZipFile(archive, "w") as handle:
        handle.writestr("runs/secret.txt", "bad")
    with pytest.raises(ValueError):
        extract_evidence(archive, destination)
    assert not (target / "secret.txt").exists()
