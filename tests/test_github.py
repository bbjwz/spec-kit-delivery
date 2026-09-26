import pytest
from speckit_delivery.github import eligible_reviews
from speckit_delivery.models import Policy


@pytest.fixture
def policy():
    return Policy(repository="owner/repo", agent="agent", approvers=["human"])


def review(id=1, user="human", state="APPROVED", head="current", body="delivery-accept: abc", type="User"):
    return {
        "id": id,
        "user": {"login": user, "type": type},
        "state": state,
        "commit_id": head,
        "body": body,
        "submitted_at": "2026-01-01T00:00:00Z",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"user": "agent"},
        {"head": "old"},
        {"state": "DISMISSED"},
        {"state": "CHANGES_REQUESTED"},
        {"type": "Bot"},
        {"body": "looks good"},
    ],
)
def test_invalid_reviews(policy, change):
    assert not eligible_reviews([review(**change)], policy, "agent", "current", "delivery-accept: abc")


def test_latest_review_and_author_separation(policy):
    assert eligible_reviews([review()], policy, "agent", "current", "delivery-accept: abc")
    assert not eligible_reviews([review()], policy, "human", "current", "delivery-accept: abc")
    assert not eligible_reviews([review(), review(id=2, state="DISMISSED")], policy, "agent")
    assert not eligible_reviews([review(), review(id=2, state="CHANGES_REQUESTED")], policy, "agent")


def test_agent_cannot_be_human():
    with pytest.raises(ValueError, match="agent identity"):
        Policy(repository="owner/repo", agent="agent", approvers=["AGENT"])


def test_protection_unavailable_is_not_acceptance(monkeypatch):
    from speckit_delivery.github import GitHub, GitHubError

    github = GitHub("owner/repo")

    def blocked(*args, **kwargs):
        raise GitHubError("private protection unavailable")

    monkeypatch.setattr(github, "policy", blocked)
    with pytest.raises(GitHubError, match="protection unavailable"):
        github.final_approval(1, "current", "abc")


def test_final_acceptance_requires_exact_ci_artifact_and_fresh_review(monkeypatch, policy):
    from speckit_delivery.github import GitHub, GitHubError

    github = GitHub("owner/repo")
    pr = {"head": {"sha": "current"}, "state": "open", "user": {"login": "agent"}}
    approved = review()
    approved["submitted_at"] = "2026-01-02T00:00:00Z"
    monkeypatch.setattr(github, "review_context", lambda *a, **k: (policy, "trusted", pr, [approved]))
    monkeypatch.setattr(github, "file", lambda *a: "trusted workflow")
    artifact = {"name": "delivery-evidence-abc", "expired": False}
    run = {
        "id": 1,
        "head_sha": "current",
        "conclusion": "success",
        "event": "pull_request",
        "pull_requests": [{"number": 1}],
        "updated_at": "2026-01-01T00:00:00Z",
    }
    monkeypatch.setattr(
        github,
        "api",
        lambda path: {"artifacts": [artifact]} if path.endswith("/artifacts") else {"workflow_runs": [run]},
    )
    assert github.final_approval(1, "current", "abc")["reviewer"] == "human"
    artifact["expired"] = True
    with pytest.raises(GitHubError, match="exact evidence"):
        github.final_approval(1, "current", "abc")
    artifact["expired"] = False
    approved["submitted_at"] = "2025-01-01T00:00:00Z"
    with pytest.raises(GitHubError, match="predates"):
        github.final_approval(1, "current", "abc")
