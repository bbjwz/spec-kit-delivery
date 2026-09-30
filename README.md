# Spec Kit Delivery

An independent GitHub Spec Kit extension for proving delivery against an approved plan and
presenting the results to stakeholders. The first integration is Codex on macOS/Linux.

**Development status:** v0.1.0 candidate. Working tests are not human acceptance. The project
must pass its own evidence and GitHub acceptance gates before it is called complete.

```
specify → plan → tasks → approve demonstration baseline → implement
  → demonstrate → verify → L0/L1/L2 presentations → human acceptance
```

## Install

Requires Spec Kit **1.0.12**, Python 3.11+, uv, Node.js 22+, npm, Git, and authenticated GitHub CLI.
This repository is private; clone it using an authorized account. From the target Spec Kit project:

```sh
specify extension add /path/to/speckit-delivery --dev
specify preset add --dev /path/to/speckit-delivery/presets/delivery-gate
specify workflow add /path/to/speckit-delivery/workflows/delivery --dev
npm --prefix .specify/extensions/delivery ci --ignore-scripts
uv run --with playwright playwright install chromium
```

Install browser binaries using the same resolved Playwright version as the runner; using the
runner's uv environment or this repository's locked environment avoids version mismatches.

Agentstandards is optional. Its pre-task architecture gate and this extension's implementation
wrapper affect different commands. Delivery never sends source or evidence to the council.

## Commands

Codex exposes `$speckit-delivery-plan`, `-demo`, `-verify`, `-present`, `-status`, and `-gate`.
The CLI always emits JSON, and verification/gating failures return nonzero:

```sh
speckit-delivery --feature specs/001-feature plan --mapping specs/001-feature/delivery/mapping.yml
speckit-delivery --feature specs/001-feature gate --phase baseline --baseline-pr 12
speckit-delivery --feature specs/001-feature demo --baseline-pr 12
speckit-delivery --feature specs/001-feature present --baseline-pr 12
speckit-delivery --feature specs/001-feature verify --baseline-pr 12 --pr 13
speckit-delivery --feature specs/001-feature gate --baseline-pr 12 --pr 13
```

For installed extensions, substitute `uv run --script
.specify/extensions/delivery/scripts/python/delivery.py` for `speckit-delivery`.
Global options precede the command. Use `--project-root` for a project outside the current directory.

## Establish the baseline

1. Finish Spec Kit `spec.md`, `plan.md`, and `tasks.md`.
2. Author `delivery/mapping.yml` using [the example](examples/mapping.yml). Map every task and
   requirement/acceptance criterion to explicit assertions. Human review verifies semantic coverage;
   a machine cannot determine whether arbitrary prose was interpreted completely.
3. Run `plan`. It snapshots all three documents and retains every baseline revision. Checkbox updates
   are normalized; obligation changes require another baseline and approval.
4. Open a **separate planning PR** as the agent. A configured human submits an approving review whose
   body includes the exact line printed by the CLI: `delivery-baseline: <digest>`.
5. Freeze that planning branch. Develop implementation on a separate branch carrying the approved
   baseline. Do not push implementation commits into the planning PR: stale-review dismissal would
   correctly revoke its approval. The planning PR may be merged by a human; no command merges it.

A required regression scenario is part of every baseline. One scenario may cover several obligations,
but checking task boxes, opening a page, taking a screenshot, or returning HTTP 200 alone is insufficient.
API scenarios assert response content; persistence and side effects need explicit follow-up scenarios.
UI scenarios use CSS selectors with `goto`, `fill`, `click`, `assert_text`, and `assert_visible`.
CLI commands are argv arrays, not implicit shell commands. Inspection scenarios assert repository file
contents. Supported operators are `equals`, `contains`, and `exists` (with `value: true`).

## Execution, retries, and evidence

`demo` verifies baseline approval, then executes all scenarios and records observed results. Repair
within approved scope, then rerun with `--repair-of <run-id>`. The runner also automatically continues
an existing failed attempt, so omitting that flag does not reset the three-cycle limit. All regression
checks rerun. Exhaustion requires human direction and a newly approved baseline; never delete history.

```
specs/<feature>/delivery/
  baseline.json                  # tracked, exact approved obligations and scenarios
  baselines/<digest>.json         # tracked baseline history, including removed obligations
  mapping.yml                    # agent-authored input
  runs/<id>/run.json              # observed execution, source fingerprints and environment
  runs/<id>/<scenario>/           # assertions, screenshots and traces
  presentations/content.json     # shared source for both presentation formats
  presentations/L0.html + L0.pptx # also L1 and L2
  presentations/runbook.md
  presentations/manifest.json
  verification.json
```

Generated evidence and decks are ignored by Git. Keep the whole delivery folder together for relative
links; export it as a private CI artifact rather than committing recordings. Source manifests include
tracked and nonignored files, including tests, baseline, and policy. Build products must be gitignored.
`verify` rejects changed source, definitions, missing results, modified files, and stale presentations.
Hashes establish integrity/freshness; they do not make local files tamper-proof. Trusted CI reruns the
scenarios and publishes the exact package digest that a human must review.

Status is `BLOCKED`, `READY_FOR_REVIEW`, or `ACCEPTED`. A locally verified run can be ready for review
but cannot self-approve. Final acceptance requires a clean committed checkout, live GitHub checks,
a current human review of the evidence digest, and the exact CI artifact at that revision.

## Presentations

One content model produces browser slides and editable PowerPoint, speaker notes, evidence links,
and a repeatable runbook. L0 covers outcome and decision (3–5 minutes); L1 covers capabilities and
journeys (10–15 minutes); L2 covers implementation, verification, and operations (20–30 minutes).
Durations are targets, not timers. Long content paginates. Brand name and accent are configurable in
the baseline. Benefits remain labelled expected unless separately measured; passing tests never
becomes an invented financial result. Draft decks disclose blockers and do not claim acceptance.

The portable extension uses PptxGenJS for export, independently of Codex's bundled document runtime.
Screenshots are embedded as evidence; text stays editable. Inspect rendered slides before sharing.

## GitHub enforcement

See [GitHub setup](docs/github-setup.md). Trusted policy is read from `.delivery-policy.yml` on the
protected default branch, never from the implementation branch. The configured agent cannot approve.
The reviewer must approve **after** successful CI, on the current revision, and include
`delivery-accept: <evidence digest>` in the review body. Dismissed, stale, bot, wrong-author, and
requested-changes reviews do not satisfy acceptance. No local approval boolean exists.

Private repositories without the necessary GitHub protection plan remain blocked. Installation does
not grant credentials, change billing, make repositories public, or silently disable enforcement.

## Development

```sh
uv sync --locked --extra test
npm ci --ignore-scripts
uv run playwright install chromium
uv run ruff check .
uv run ruff format --check .
uv run pytest --cov=speckit_delivery
uv build
uv run python scripts/build_release.py
AGENTSTANDARDS_CHECKOUT=/path/to/agentstandards bash scripts/verify_install.sh
```

Tests use explicitly named fake GitHub fixtures inside disposable test repositories. Those fixtures
are not reachable through the CLI and are never evidence of real human approval.

## Trust and limitations

Run approved project commands only in an isolated development or CI environment with synthetic data.
This runner is not a sandbox: source code and a shell explicitly named in argv can access the user's
machine. Credentials are not forwarded as environment variables, but local files and OS credential
stores remain accessible to project code. UI traces may contain application data; review all evidence
before sharing. Production credentials, arbitrary native desktop apps, and PowerPoint template import
are outside v1. Human review remains responsible for whether assertions are meaningful and sufficient.

For wheel installations, run `npm ci --ignore-scripts --prefix <installed speckit_delivery directory>`
to install the bundled PowerPoint dependencies. In macOS synced folders, Python 3.14 may skip hidden
editable-install `.pth` files; use the extension launcher or `PYTHONPATH=runtime uv run ...` for local
source development. The clean wheel and extension launchers do not depend on editable-path loading.
