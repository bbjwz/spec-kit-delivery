# GitHub enforcement setup

## Preconditions

Use a separate agent account for commits and PRs. Grant it write access, not administration.
Choose explicit human approvers (`bbjwz` initially). Agent workflows never submit their reviews.
Private repositories need a GitHub plan that supports protected branches. A 403, absent configuration,
unavailable credentials, or missing trusted workflow is a blocker, not advisory mode.

Bootstrap `.delivery-policy.yml` and reviewed workflow definitions onto the default branch through
human-reviewed PRs. Pin the delivery runner to a reviewed full commit SHA from this private repo.
Do not use the implementation PR's runner or install its Python package in the audit job.
The repository owner must provision any private-read credentials through GitHub Secrets; do not
commit tokens or grant the agent access to the human's review credentials.

Configure classic default-branch protection with:

- At least one approving human review and dismissal of stale approvals.
- Required status context `delivery-acceptance` and enforcement for administrators.
- No force pushes or branch deletion.

The v1 verifier reads classic branch protection. Repositories using only rulesets must additionally
configure equivalent classic protection; unsupported protection API access fails closed.

## Trusted workflow arrangement

There are three isolated stages. Use GitHub-hosted ephemeral runners; never run PR commands on a
self-hosted runner containing credentials.

1. **Authorize, trusted code:** `python -m speckit_delivery.ci authorize` reads GitHub policy,
   protection, the proposed feature baseline, and the human baseline review. It writes a receipt
   containing the approved baseline digest and exact implementation head SHA. No PR code executes.
2. **Execute, no privileged credentials:** a fresh job checks out the authorized candidate and runs
   `python -m speckit_delivery.ci execute --project-root ... --receipt ...` using the pinned runner.
   It runs the scenarios, generates decks, validates evidence, and publishes only `runs/`,
   `presentations/`, and `verification.json` in artifact `delivery-evidence-<digest>`.
3. **Audit, trusted code:** on human review or synchronization, a default-branch workflow downloads
   that artifact, checks out the candidate as data, and runs `python -m speckit_delivery.ci audit`.
   It never runs candidate commands or imports candidate Python. It rechecks policy, protection,
   exact head, baseline approval, integrity, the evidence-producing workflow, and human acceptance.
   Publish its result under `delivery-acceptance` for the exact candidate SHA.

Copy the three `examples/delivery-*.yml` workflows into `.github/workflows/`.
Set repository variable `DELIVERY_RUNNER_SHA` to the reviewed full runner commit SHA.
For another private repository, set `DELIVERY_RUNNER_READ_TOKEN` to a fine-grained token with
contents-read access to the runner repository only. The owner configures this credential.
Set the environment `delivery-audit` to permit deployments only from the default branch, and put
`DELIVERY_AUDIT_READ_TOKEN` there with read-only Contents, Pull requests, Actions, and Administration
permissions for this repository. The latter is needed to inspect branch protection. Never give
this token write or review-submission permissions. Do not expose it as a repository-wide secret.
The authorization and execution jobs use separate runners and a digest-bound receipt. A pending policy bootstrap must
not be confused with enforcement being active. `.delivery-request.json` selects the feature and
frozen baseline PR, for example:

```json
{"feature":"specs/001-example","baseline_pr":12}
```

The unprivileged `Delivery review signal` workflow only signals a changed review.
The default-branch acceptance workflow wakes through `workflow_run` and independently queries GitHub.
It also audits new candidate heads using `pull_request_target`. The candidate is checked out as data,
never installed, imported or executed in the audit job. The environment restriction keeps audit
credentials unavailable to PR-context workflows. No external authorization service is required.

## Evidence lifecycle

The evidence-producing workflow must match the default-branch copy byte-for-byte. A successful run
must belong to the exact PR head, publish the exact evidence digest, and precede the human review.
The reviewer opens the private artifact, reviews all levels, then submits an approving review with:

```
delivery-accept: <evidence_hash printed by verify>
```

New code, a rerun producing different evidence, dismissed approval, or a request for changes requires
another review. Expired/missing artifacts block acceptance. Download the original CI package for
local auditing; a new local rerun has a new run ID and is a different package requiring a new review.

Do not commit CI evidence into the candidate revision: that creates an avoidable SHA/evidence cycle.
Source hashes exclude generated evidence and slide outputs, while GitHub binds acceptance to the
actual commit SHA. Branch policy and workflow changes are reviewed as trust-root changes separately
from the feature they would accept.
