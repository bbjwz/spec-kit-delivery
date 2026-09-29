import json
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest
import yaml
from speckit_delivery.attestation import read_attestation
from speckit_delivery.ci import JobReceipt, execute_job, extract_attestation


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
        extract_attestation(archive, tmp_path / "attestation.json")


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
    from speckit_delivery.storage import digest, git, read

    root, feature = project
    receipt = {
        "repository": "example/project",
        "pr": 2,
        "head": git(root, "rev-parse", "HEAD"),
        "feature": str(feature.relative_to(root)),
        "baseline_pr": 1,
        "baseline_hash": digest(read(feature / "delivery/baseline.json")),
        "approval": {
            "review_id": 1,
            "reviewer": "fixture",
            "commit": "1" * 40,
            "submitted_at": "2026-01-01T00:00:00Z",
        },
    }
    result = execute_job(root, receipt)
    assert result["attestation"]["status"] == "READY_FOR_REVIEW"
    assert len(result["attestation"]["evidence_hash"]) == 64
    receipt["head"] = "wrong"
    with pytest.raises(ValueError, match="checkout"):
        execute_job(root, receipt)


def test_attestation_archive_symlink_rejected(tmp_path):
    archive = tmp_path / "evidence.zip"
    with ZipFile(archive, "w") as handle:
        info = ZipInfo("attestation.json")
        info.external_attr = 0o120777 << 16
        handle.writestr(info, "bad")
    with pytest.raises(ValueError):
        extract_attestation(archive, tmp_path / "attestation.json")


def test_public_attestation_excludes_private_evidence_and_canary_secrets(project):
    from speckit_delivery.storage import digest, git, read

    root, feature = project
    canaries = [
        "ghp_publicArtifactMustNeverContainThis",
        "AKIAIOSFODNN7EXAMPLE",
        "Bearer private-http-response-token",
        "speaker note with customer@example.invalid",
    ]
    (root / "greet.py").write_text("print(" + repr(" ".join(canaries) + " hello") + ")\n")
    subprocess.run(["git", "-C", str(root), "add", "greet.py"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=x@example.invalid",
            "commit",
            "-m",
            "canary",
        ],
        check=True,
        capture_output=True,
    )
    receipt = {
        "repository": "example/project",
        "pr": 2,
        "head": git(root, "rev-parse", "HEAD"),
        "feature": str(feature.relative_to(root)),
        "baseline_pr": 1,
        "baseline_hash": digest(read(feature / "delivery/baseline.json")),
        "approval": {
            "review_id": 1,
            "reviewer": "human",
            "commit": "1" * 40,
            "submitted_at": "2026-01-01T00:00:00Z",
        },
    }
    output = root / "public/attestation.json"
    execute_job(root, receipt, attestation_path=output, scrub_private=True)
    serialized = output.read_text()
    assert all(canary not in serialized for canary in canaries)
    assert not (feature / "delivery/runs").exists()
    assert not (feature / "delivery/presentations").exists()
    assert not (feature / "delivery/verification.json").exists()
    wrapped = read_attestation(output)
    assert wrapped["attestation"]["status"] == "READY_FOR_REVIEW"
    assert set(json.loads(serialized)) == {"attestation", "attestation_hash"}


def test_public_workflow_uploads_only_the_attestation():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/delivery-evidence.yml").read_text()
    assert "steps.execute.outputs.attestation" in workflow
    assert "delivery-attestation-" in workflow
    assert workflow.count("actions/upload-artifact@") == 1
    assert "if: ${{ vars.DELIVERY_RUNNER_SHA != '' }}" in workflow
    for forbidden in ("evidence_dir", "/runs/", "/presentations/", "verification.json"):
        assert forbidden not in workflow
