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
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from .core import check_mapping, run_demo, verify
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


def execute_job(root: Path, receipt: dict) -> dict:
    if git(root, "rev-parse", "HEAD") != receipt["head"]:
        raise ValueError("CI checkout differs from authorized revision")
    feature = root / receipt["feature"]
    authority = JobReceipt(receipt)
    run_demo(root, feature, receipt["baseline_pr"], github=authority)
    present(root, feature, receipt["baseline_pr"], github=authority)
    report = verify(root, feature, receipt["baseline_pr"], github=authority)
    if report["status"] == "BLOCKED":
        raise ValueError("CI evidence failed: " + "; ".join(report["errors"]))
    return report


def extract_evidence(archive: Path, destination: Path) -> None:
    """Reject traversal, symlink entries, oversized archives and non-evidence files."""
    destination = inside(destination.parents[2], destination)
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as zipped:
        if sum(i.file_size for i in zipped.infolist()) > 500_000_000:
            raise ValueError("evidence artifact exceeds 500 MB")
        for info in zipped.infolist():
            path = Path(info.filename)
            inside(destination, path)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("unsafe artifact path")
            if path.parts[0] not in {"runs", "presentations", "verification.json"}:
                raise ValueError("unexpected file in evidence artifact")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("symlink in evidence archive")
        zipped.extractall(destination)


def audit(repository: str, number: int, root: Path, archive: Path) -> dict:
    receipt = authorize(repository, number)
    if git(root, "rev-parse", "HEAD") != receipt["head"]:
        raise ValueError("audit checkout is not the current PR revision")
    feature = root / receipt["feature"]
    # Candidate evidence is data only. Never import modules or run project commands.
    extract_evidence(archive, feature / "delivery")
    return verify(root, feature, receipt["baseline_pr"], pr=number, github=GitHub(repository))


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
    packages = [a for a in artifacts if re.fullmatch(r"delivery-evidence-[0-9a-f]{64}", a["name"]) and not a["expired"]]
    if len(packages) != 1:
        raise ValueError("exactly one current evidence package is required")
    with tempfile.TemporaryDirectory(prefix="delivery-audit-") as tmp:
        archive = Path(tmp) / "evidence.zip"
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
        result = execute_job(args.project_root.resolve(), read(args.receipt))
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a") as handle:
                handle.write(f"evidence_hash={result['evidence_hash']}\n")
                feature = read(args.receipt)["feature"]
                handle.write(f"evidence_dir={args.project_root.resolve() / feature / 'delivery'}\n")
    else:
        if args.archive:
            result = audit(args.repository, args.pr, args.project_root.resolve(), args.archive)
        else:
            result = fetch_and_audit(args.repository, args.pr, args.project_root.resolve())
    print(json.dumps(result, indent=2))
    return (
        0
        if result.get("status") != "BLOCKED" and (args.command != "audit" or result.get("status") == "ACCEPTED")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
