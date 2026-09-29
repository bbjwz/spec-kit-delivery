"""Create and validate the only artifact permitted in public CI.

Raw command output, HTTP bodies, browser captures, traces, speaker notes, and
presentations stay in the ephemeral runner workspace or an explicitly private
store.  The public artifact is an allowlisted commitment to those results.
"""

from __future__ import annotations

import re
from pathlib import Path

from .core import current_run, load_baseline, runner_hash
from .storage import digest, git, now, read, write

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
RUN_ID = re.compile(r"^[0-9a-f]{32}$")
FEATURE = re.compile(r"^specs/[A-Za-z0-9_-]+$")
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
PRESENTATIONS = {f"{level}.{suffix}" for level in ("L0", "L1", "L2") for suffix in ("html", "pptx")}

TOP_LEVEL_KEYS = {
    "schema_version",
    "repository",
    "pr",
    "head",
    "feature",
    "baseline_pr",
    "baseline_hash",
    "baseline_approval",
    "runner_revision",
    "runner_hash",
    "source_hash",
    "run_id",
    "generated_at",
    "status",
    "evidence_hash",
    "verification_hash",
    "scenarios",
    "obligations",
    "presentation_artifacts",
}


def _trusted_revision() -> str:
    return git(Path(__file__).resolve().parents[2], "rev-parse", "HEAD")


def build_attestation(root: Path, feature: Path, receipt: dict, report: dict) -> dict:
    """Project verified private evidence into a fixed, non-sensitive schema."""
    if report.get("status") != "READY_FOR_REVIEW" or report.get("errors"):
        raise ValueError("only successful verification can produce a public attestation")
    baseline = load_baseline(feature)
    _, run = current_run(feature)
    presentations = read(feature / "delivery/presentations/manifest.json")
    scenario_defs = {scenario.id: scenario for scenario in baseline.scenarios}
    records = {record["id"]: record for record in run["records"]}
    scenarios = []
    for scenario_id in sorted(scenario_defs):
        scenario = scenario_defs[scenario_id]
        record = records[scenario_id]
        scenario_artifacts = {
            name: checksum for name, checksum in run["artifacts"].items() if name.startswith(f"{scenario_id}/")
        }
        scenarios.append(
            {
                "id": scenario_id,
                "kind": scenario.kind,
                "obligations": sorted(scenario.obligations),
                "passed": record["passed"] is True,
                "scenario_hash": record["scenario_hash"],
                "result_hash": digest(record),
                "artifact_set_hash": digest(scenario_artifacts),
                "artifact_count": len(scenario_artifacts),
            }
        )
    obligations = []
    for obligation in sorted(baseline.obligations, key=lambda item: item.id):
        coverage = sorted(s.id for s in baseline.scenarios if obligation.id in s.obligations)
        obligations.append(
            {
                "id": obligation.id,
                "scenarios": coverage,
                "passed": bool(coverage) and all(records[item]["passed"] is True for item in coverage),
            }
        )
    approval = receipt["approval"]
    payload = {
        "schema_version": 1,
        "repository": receipt["repository"],
        "pr": receipt["pr"],
        "head": receipt["head"],
        "feature": receipt["feature"],
        "baseline_pr": receipt["baseline_pr"],
        "baseline_hash": receipt["baseline_hash"],
        "baseline_approval": {
            "review_id": approval["review_id"],
            "reviewer": approval["reviewer"],
            "commit": approval["commit"],
            "submitted_at": approval["submitted_at"],
        },
        "runner_revision": _trusted_revision(),
        "runner_hash": runner_hash(),
        "source_hash": run["source_hash"],
        "run_id": run["run_id"],
        "generated_at": now(),
        "status": "READY_FOR_REVIEW",
        "evidence_hash": report["evidence_hash"],
        "verification_hash": digest(
            {
                "status": report["status"],
                "evidence_hash": report["evidence_hash"],
                "error_count": len(report["errors"]),
                "acceptance_blocker_count": len(report["acceptance_blockers"]),
            }
        ),
        "scenarios": scenarios,
        "obligations": obligations,
        "presentation_artifacts": {name: presentations["artifacts"][name] for name in sorted(PRESENTATIONS)},
    }
    validate_attestation(payload)
    return payload


def envelope(payload: dict) -> dict:
    validate_attestation(payload)
    return {"attestation": payload, "attestation_hash": digest(payload)}


def write_attestation(path: Path, payload: dict) -> dict:
    wrapped = envelope(payload)
    write(path, wrapped)
    return wrapped


def read_attestation(path: Path) -> dict:
    wrapped = read(path)
    if not isinstance(wrapped, dict) or set(wrapped) != {"attestation", "attestation_hash"}:
        raise ValueError("invalid public attestation envelope")
    payload = wrapped["attestation"]
    validate_attestation(payload)
    if wrapped["attestation_hash"] != digest(payload):
        raise ValueError("public attestation hash mismatch")
    return wrapped


def validate_attestation(payload: dict) -> None:
    if not isinstance(payload, dict) or set(payload) != TOP_LEVEL_KEYS:
        raise ValueError("public attestation fields differ from the allowlist")
    if payload["schema_version"] != 1 or payload["status"] != "READY_FOR_REVIEW":
        raise ValueError("unsupported public attestation")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", payload["repository"]):
        raise ValueError("invalid repository in public attestation")
    if not isinstance(payload["pr"], int) or not isinstance(payload["baseline_pr"], int):
        raise ValueError("invalid PR identity in public attestation")
    if not SHA.fullmatch(payload["head"]) or not SHA.fullmatch(payload["runner_revision"]):
        raise ValueError("invalid revision in public attestation")
    if not FEATURE.fullmatch(payload["feature"]) or not RUN_ID.fullmatch(payload["run_id"]):
        raise ValueError("invalid feature or run identity in public attestation")
    for name in ("baseline_hash", "runner_hash", "source_hash", "evidence_hash", "verification_hash"):
        if not SHA256.fullmatch(payload[name]):
            raise ValueError(f"invalid {name} in public attestation")
    approval = payload["baseline_approval"]
    if not isinstance(approval, dict) or set(approval) != {"review_id", "reviewer", "commit", "submitted_at"}:
        raise ValueError("invalid baseline approval provenance")
    if not isinstance(approval["review_id"], int) or not approval["reviewer"] or not SHA.fullmatch(approval["commit"]):
        raise ValueError("invalid baseline approval identity")
    scenarios = payload["scenarios"]
    obligations = payload["obligations"]
    if not scenarios or not obligations:
        raise ValueError("public attestation requires scenarios and obligations")
    if len({item["id"] for item in scenarios}) != len(scenarios):
        raise ValueError("duplicate public scenario IDs")
    for item in scenarios:
        if set(item) != {
            "id",
            "kind",
            "obligations",
            "passed",
            "scenario_hash",
            "result_hash",
            "artifact_set_hash",
            "artifact_count",
        }:
            raise ValueError("public scenario fields differ from the allowlist")
        if not IDENTIFIER.fullmatch(item["id"]) or item["kind"] not in {"cli", "api", "ui", "inspection"}:
            raise ValueError("invalid public scenario identity")
        if item["passed"] is not True or not isinstance(item["artifact_count"], int) or item["artifact_count"] < 1:
            raise ValueError("public scenario did not pass or has no evidence")
        if any(not SHA256.fullmatch(item[name]) for name in ("scenario_hash", "result_hash", "artifact_set_hash")):
            raise ValueError("invalid public scenario hash")
        if not item["obligations"] or any(not IDENTIFIER.fullmatch(value) for value in item["obligations"]):
            raise ValueError("invalid public scenario coverage")
    if len({item["id"] for item in obligations}) != len(obligations):
        raise ValueError("duplicate public obligation IDs")
    for item in obligations:
        if set(item) != {"id", "scenarios", "passed"} or item["passed"] is not True:
            raise ValueError("public obligation fields differ from the allowlist")
        if not IDENTIFIER.fullmatch(item["id"]) or not item["scenarios"]:
            raise ValueError("invalid public obligation coverage")
    artifacts = payload["presentation_artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != PRESENTATIONS:
        raise ValueError("all L0, L1, and L2 presentation commitments are required")
    if any(not SHA256.fullmatch(value) for value in artifacts.values()):
        raise ValueError("invalid presentation commitment")
