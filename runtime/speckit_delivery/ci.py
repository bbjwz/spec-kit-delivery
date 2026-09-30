"""CI entrypoints. Run this module from a pinned trusted checkout, never from PR source.

An authorization receipt is transported between isolated jobs. It is not a local
acceptance mechanism: final acceptance independently checks live GitHub authority,
workflow provenance, the CI artifact digest, and an exact human review.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from .attestation import build_attestation, envelope, read_attestation, write_attestation
from .core import check_mapping, run_demo, runner_hash, verify
from .github import GitHub
from .models import Baseline
from .presentation import present
from .storage import digest, git, inside, normalized_document, read, write


def authorize(repository: str, number: int) -> dict:
    gh = GitHub(repository)
    _, _, pr, _ = gh.review_context(number)
    head = pr["head"]["sha"]
    request = json.loads(gh.file(".delivery-request.json", head))
    feature = request["feature"]
    if not re.fullmatch(r"specs/[A-Za-z0-9_-]+", feature):
        raise ValueError("invalid requested feature")
    baseline = Baseline.model_validate(json.loads(gh.file(f"{feature}/delivery/baseline.json", head)))
    check_mapping(baseline)
    for name, text in baseline.documents.items():
        if normalized_document(name, gh.file(f"{feature}/{name}", head)) != text:
            raise ValueError("head documents differ from the baseline")
    baseline_hash = digest(baseline.model_dump(mode="json"))
    approved = gh.baseline_approval(request["baseline_pr"], f"{feature}/delivery/baseline.json", baseline_hash)
    return {
        "repository": repository,
        "head": head,
        "pr": number,
        "feature": feature,
        "baseline_pr": request["baseline_pr"],
        "baseline_hash": baseline_hash,
        "approval": approved,
    }


class JobReceipt:
    def __init__(self, data):
        self.data = data

    def baseline_approval(self, number, path, checksum):
        if number != self.data["baseline_pr"] or checksum != self.data["baseline_hash"]:
            raise ValueError("isolated CI receipt differs from the executed baseline")
        if path != self.data["feature"] + "/delivery/baseline.json":
            raise ValueError("CI receipt feature mismatch")
        return self.data["approval"]


def _remove_private_outputs(feature: Path) -> None:
    for name in ("runs", "presentations"):
        shutil.rmtree(feature / "delivery" / name, ignore_errors=True)
    (feature / "delivery/verification.json").unlink(missing_ok=True)


def execute_job(
    root: Path,
    receipt: dict,
    *,
    attestation_path: Path | None = None,
    scrub_private: bool = False,
) -> dict:
    if git(root, "rev-parse", "HEAD") != receipt["head"]:
        raise ValueError("CI checkout differs from authorized revision")
    feature = root / receipt["feature"]
    authority = JobReceipt(receipt)
    try:
        run_demo(root, feature, receipt["baseline_pr"], github=authority)
        present(root, feature, receipt["baseline_pr"], github=authority)
        report = verify(root, feature, receipt["baseline_pr"], github=authority)
        if report["status"] == "BLOCKED":
            raise ValueError("CI evidence failed; inspect the private runner workspace")
        payload = build_attestation(root, feature, receipt, report)
        wrapped = write_attestation(attestation_path, payload) if attestation_path else envelope(payload)
        return wrapped
    finally:
        if scrub_private:
            _remove_private_outputs(feature)


def extract_attestation(archive: Path, destination: Path) -> Path:
    """Accept one small regular attestation file and reject every raw-evidence path."""
    destination = inside(destination.parent, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as zipped:
        entries = [info for info in zipped.infolist() if not info.is_dir()]
        if len(entries) != 1 or Path(entries[0].filename).name != "attestation.json":
            raise ValueError("public artifact must contain only attestation.json")
        info = entries[0]
        if info.file_size > 1_000_000:
            raise ValueError("public attestation exceeds 1 MB")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("symlink in public attestation archive")
        destination.write_bytes(zipped.read(info))
    return destination


def audit(repository: str, number: int, root: Path, archive: Path) -> dict:
    receipt = authorize(repository, number)
    if git(root, "rev-parse", "HEAD") != receipt["head"]:
        raise ValueError("audit checkout is not the current PR revision")
    # Candidate output is data only. Never import modules or run project commands.
    with tempfile.TemporaryDirectory(prefix="delivery-attestation-") as tmp:
        path = extract_attestation(archive, Path(tmp) / "attestation.json")
        wrapped = read_attestation(path)
    attestation = wrapped["attestation"]
    expected = {
        "repository": repository,
        "pr": number,
        "head": receipt["head"],
        "feature": receipt["feature"],
        "baseline_pr": receipt["baseline_pr"],
        "baseline_hash": receipt["baseline_hash"],
        "baseline_approval": receipt["approval"],
    }
    for key, value in expected.items():
        if attestation[key] != value:
            raise ValueError(f"public attestation {key} differs from current GitHub authority")
    if attestation["runner_revision"] != git(Path(__file__).resolve().parents[2], "rev-parse", "HEAD"):
        raise ValueError("public attestation was produced by a different trusted runner revision")
    if attestation["runner_hash"] != runner_hash():
        raise ValueError("public attestation runner fingerprint differs")
    baseline = Baseline.model_validate(
        json.loads(GitHub(repository).file(f"{receipt['feature']}/delivery/baseline.json", receipt["head"]))
    )
    scenario_by_id = {item["id"]: item for item in attestation["scenarios"]}
    if set(scenario_by_id) != {scenario.id for scenario in baseline.scenarios}:
        raise ValueError("public attestation scenario coverage differs from the baseline")
    for scenario in baseline.scenarios:
        item = scenario_by_id[scenario.id]
        scenario_changed = item["scenario_hash"] != digest(scenario.model_dump(mode="json"))
        mapping_changed = item["obligations"] != sorted(scenario.obligations)
        if scenario_changed or mapping_changed:
            raise ValueError("public attestation scenario mapping differs from the baseline")
    obligation_by_id = {item["id"]: item for item in attestation["obligations"]}
    if set(obligation_by_id) != {obligation.id for obligation in baseline.obligations}:
        raise ValueError("public attestation obligation coverage differs from the baseline")
    acceptance = GitHub(repository).final_approval(number, receipt["head"], attestation["evidence_hash"])
    return {
        "schema_version": 1,
        "status": "ACCEPTED",
        "head": receipt["head"],
        "evidence_hash": attestation["evidence_hash"],
        "attestation_hash": wrapped["attestation_hash"],
        "acceptance": acceptance,
    }


def fetch_and_audit(repository: str, number: int, root: Path) -> dict:
    gh = GitHub(repository)
    policy, _, pr, _ = gh.review_context(number, require_protection=True)
    head = pr["head"]["sha"]
    workflow = Path(policy.verification_workflow).name
    runs = gh.api(f"repos/{repository}/actions/workflows/{workflow}/runs?head_sha={head}&event=pull_request")[
        "workflow_runs"
    ]
    if not runs:
        raise ValueError("no evidence workflow run for this revision")
    run = max(runs, key=lambda item: item["id"])
    if run["conclusion"] != "success":
        raise ValueError("latest evidence workflow has not succeeded")
    artifacts = gh.api(f"repos/{repository}/actions/runs/{run['id']}/artifacts")["artifacts"]
    packages = [
        a for a in artifacts if re.fullmatch(r"delivery-attestation-[0-9a-f]{64}", a["name"]) and not a["expired"]
    ]
    if len(packages) != 1:
        raise ValueError("exactly one current public attestation is required")
    with tempfile.TemporaryDirectory(prefix="delivery-audit-") as tmp:
        archive = Path(tmp) / "attestation.zip"
        with archive.open("wb") as handle:
            subprocess.run(
                ["gh", "api", f"repos/{repository}/actions/artifacts/{packages[0]['id']}/zip"],
                stdout=handle,
                stderr=subprocess.PIPE,
                check=True,
                timeout=120,
            )
        return audit(repository, number, root, archive)


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    auth = commands.add_parser("authorize")
    auth.add_argument("--repository", required=True)
    auth.add_argument("--pr", type=int, required=True)
    auth.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("execute")
    execute.add_argument("--project-root", type=Path, required=True)
    execute.add_argument("--receipt", type=Path, required=True)
    execute.add_argument("--attestation", type=Path, required=True)
    execute.add_argument("--scrub-private", action="store_true")
    verify_parser = commands.add_parser("audit")
    verify_parser.add_argument("--repository", required=True)
    verify_parser.add_argument("--pr", type=int, required=True)
    verify_parser.add_argument("--project-root", type=Path, required=True)
    verify_parser.add_argument("--archive", type=Path)
    args = parser.parse_args(argv)
    if args.command == "authorize":
        result = authorize(args.repository, args.pr)
        write(args.output, result)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a") as handle:
                encoded = base64.b64encode(json.dumps(result).encode()).decode()
                handle.write(f"receipt={encoded}\nhead={result['head']}\n")
    elif args.command == "execute":
        result = execute_job(
            args.project_root.resolve(),
            read(args.receipt),
            attestation_path=args.attestation.resolve(),
            scrub_private=args.scrub_private,
        )
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a") as handle:
                handle.write(f"evidence_hash={result['attestation']['evidence_hash']}\n")
                handle.write(f"attestation_hash={result['attestation_hash']}\n")
                handle.write(f"attestation={args.attestation.resolve()}\n")
    else:
        if args.archive:
            result = audit(args.repository, args.pr, args.project_root.resolve(), args.archive)
        else:
            result = fetch_and_audit(args.repository, args.pr, args.project_root.resolve())
    public_result = (
        result
        if args.command == "audit"
        else {
            "status": result["attestation"]["status"] if args.command == "execute" else "AUTHORIZED",
            "head": result["attestation"]["head"] if args.command == "execute" else result["head"],
            "evidence_hash": result["attestation"]["evidence_hash"] if args.command == "execute" else None,
            "attestation_hash": result["attestation_hash"] if args.command == "execute" else None,
        }
    )
    print(json.dumps(public_result, indent=2))
    return (
        0
        if public_result.get("status") != "BLOCKED"
        and (args.command != "audit" or public_result.get("status") == "ACCEPTED")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
