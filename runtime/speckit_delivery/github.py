"""Read GitHub authority, never accept local approval assertions.

Policy and workflow definitions come from the protected default branch. A separate
runner checkout is required in CI; do not execute PR Python with privileged tokens.
"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from urllib.parse import quote

import yaml

from .models import Policy
from .storage import digest, git


class GitHubError(ValueError):
    pass


class GitHub:
    def __init__(self, repository: str):
        self.repository = repository

    def api(self, path: str):
        result = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=45)
        if result.returncode:
            # Do not surface response bodies which could include private data.
            raise GitHubError(f"GitHub could not read {path.split('?')[0]}")
        return json.loads(result.stdout)

    def pages(self, path: str) -> list:
        items = []
        for page in range(1, 101):
            separator = "&" if "?" in path else "?"
            data = self.api(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(data, list):
                raise GitHubError("unexpected paginated response")
            items.extend(data)
            if len(data) < 100:
                return items
        raise GitHubError("pagination limit exceeded; refusing incomplete review history")

    def file(self, path: str, ref: str) -> str:
        result = self.api(f"repos/{self.repository}/contents/{quote(path, safe='/')}?ref={quote(ref, safe='')}")
        return base64.b64decode(result["content"]).decode()

    def policy(self, require_protection: bool = True) -> tuple[Policy, str, dict]:
        repo = self.api(f"repos/{self.repository}")
        branch = self.api(f"repos/{self.repository}/branches/{quote(repo['default_branch'], safe='')}")
        ref = branch["commit"]["sha"]
        policy = Policy.model_validate(yaml.safe_load(self.file(".delivery-policy.yml", ref)))
        if policy.repository != self.repository:
            raise GitHubError("trusted policy repository mismatch")
        if not require_protection:
            return policy, ref, repo
        protection = self.api(f"repos/{self.repository}/branches/{quote(repo['default_branch'], safe='')}/protection")
        reviews = protection.get("required_pull_request_reviews") or {}
        statuses = protection.get("required_status_checks") or {}
        if not (
            branch.get("protected")
            and protection.get("enforce_admins", {}).get("enabled")
            and reviews.get("required_approving_review_count", 0) >= 1
            and reviews.get("dismiss_stale_reviews")
            and policy.required_check in statuses.get("contexts", [])
        ):
            raise GitHubError("required protected-branch review/check settings are not enforced")
        return policy, ref, repo

    def review_context(self, number: int, require_protection: bool = False):
        policy, trusted_ref, repo = self.policy(require_protection)
        pr = self.api(f"repos/{self.repository}/pulls/{number}")
        if pr["base"]["repo"]["full_name"] != self.repository:
            raise GitHubError("PR targets a different repository")
        if pr["base"]["ref"] != repo["default_branch"]:
            raise GitHubError("PR does not target the protected default branch")
        if pr["user"]["login"].casefold() != policy.agent.casefold():
            raise GitHubError("PR author is not the configured agent identity")
        reviews = self.pages(f"repos/{self.repository}/pulls/{number}/reviews")
        return policy, trusted_ref, pr, reviews

    def baseline_approval(self, number: int, baseline_path: str, baseline_hash: str) -> dict:
        policy, _, pr, reviews = self.review_context(number)
        commits = {c["sha"] for c in self.pages(f"repos/{self.repository}/pulls/{number}/commits")}
        # Baseline approval is a dedicated review marker; ordinary implementation
        # review text cannot accidentally approve changes to acceptance criteria.
        marker = f"delivery-baseline: {baseline_hash}"
        candidates = eligible_reviews(reviews, policy, pr["user"]["login"], marker=marker)
        for review in reversed(candidates):
            if review["commit_id"] not in commits:
                continue
            saved = yaml.safe_load(self.file(baseline_path, review["commit_id"]))
            if digest(saved) == baseline_hash:
                return {
                    "review_id": review["id"],
                    "reviewer": review["user"]["login"],
                    "commit": review["commit_id"],
                    "submitted_at": review["submitted_at"],
                }
        raise GitHubError("no current human approval of this baseline digest")

    def final_approval(self, number: int, head: str, evidence_hash: str) -> dict:
        policy, trusted_ref, pr, reviews = self.review_context(number, require_protection=True)
        if pr["head"]["sha"] != head or pr["state"] != "open":
            raise GitHubError("PR head differs from the verified revision or PR is closed")
        if self.file(policy.verification_workflow, head) != self.file(policy.verification_workflow, trusted_ref):
            raise GitHubError("verification workflow differs from the trusted default branch")
        runs = self.api(
            f"repos/{self.repository}/actions/workflows/"
            f"{quote(Path(policy.verification_workflow).name, safe='')}/runs"
            f"?head_sha={head}&event=pull_request&per_page=100"
        )["workflow_runs"]
        latest_id = max((r["id"] for r in runs), default=None)
        valid_runs = [
            r
            for r in runs
            if r["id"] == latest_id
            and r["head_sha"] == head
            and r["conclusion"] == "success"
            and r.get("event") == "pull_request"
            and any(p["number"] == number for p in r.get("pull_requests", []))
        ]
        if not valid_runs:
            raise GitHubError("no successful trusted verification workflow for this PR revision")
        run = max(valid_runs, key=lambda item: item["id"])
        artifacts = self.api(f"repos/{self.repository}/actions/runs/{run['id']}/artifacts")["artifacts"]
        if not any(a["name"] == f"delivery-attestation-{evidence_hash}" and not a["expired"] for a in artifacts):
            raise GitHubError("CI did not publish the public attestation for this exact evidence digest")
        marker = f"delivery-accept: {evidence_hash}"
        eligible = eligible_reviews(reviews, policy, pr["user"]["login"], head, marker)
        if not eligible:
            raise GitHubError("human acceptance of this revision and evidence package is missing")
        review = eligible[-1]
        run = max(valid_runs, key=lambda item: item["id"])
        if review["submitted_at"] < run["updated_at"]:
            raise GitHubError("human acceptance predates the current verification run")
        return {
            "review_id": review["id"],
            "reviewer": review["user"]["login"],
            "commit": head,
            "workflow_run": run["id"],
            "evidence_hash": evidence_hash,
        }


def eligible_reviews(reviews, policy, author, head=None, marker=None):
    """Latest decisive review per human; dismissed or requested-changes revoke approval."""
    latest = {}
    allowed = {a.casefold() for a in policy.approvers}
    for review in sorted(reviews, key=lambda r: r["id"]):
        user = review["user"]
        login = user["login"].casefold()
        if login not in allowed or login in {author.casefold(), policy.agent.casefold()}:
            continue
        if user.get("type") != "User":
            continue
        if review["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest[login] = review
    # An unresolved change request from any designated reviewer blocks acceptance.
    if any(r["state"] == "CHANGES_REQUESTED" for r in latest.values()):
        return []
    return [
        r
        for r in latest.values()
        if r["state"] == "APPROVED"
        and (head is None or r["commit_id"] == head)
        and (marker is None or marker in (r.get("body") or "").splitlines())
    ]


def github_for(root: Path) -> GitHub:
    """Local policy selects a repository only; authority always comes from GitHub."""
    import re

    try:
        remote = git(root, "remote", "get-url", "origin")
    except subprocess.CalledProcessError as exc:
        raise GitHubError("origin is unavailable") from exc
    match = re.fullmatch(r"(?:https://github.com/|git@github.com:)([\w.-]+/[\w.-]+?)(?:\.git)?", remote)
    if not match:
        raise GitHubError("origin must be a GitHub repository")
    return GitHub(match[1])
