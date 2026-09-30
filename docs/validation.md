# Validation record

Human acceptance: PENDING

This candidate is authorized for implementation by the user-approved plan. It has not received
an actual GitHub baseline review or final delivery acceptance. Unit/integration tests use explicitly
labelled authority fixtures; no production approval or passing gate has been fabricated.

Live environment checks on 2026-09-26:

- Public bbjwz/spec-kit-delivery repository exists.
- barthisagent is authenticated separately and has write access; bbjwz remains the human reviewer.
- GitHub returned HTTP 403 when querying repository rulesets: private protection needs GitHub Pro.
- Default branch initialization is awaiting explicit permission under the user's publishing policy.

The self baseline covers the implementation and its honest status reporting. Final human acceptance
is a separate mandatory gate, not a self-asserted task. The real self-demo has not run under an approved
GitHub baseline. Establish the CI trust root and human reviews before any v1 completion/release claim.

## Local verification

- 39 tests passed on Python 3.11 and Python 3.14, covering execution adapters, CLI behavior, evidence tampering,
  source freshness, repair limits, GitHub review eligibility, CI receipts, archive boundaries,
  PowerPoint editability, notes, screenshot export, and browser navigation.
- Ruff lint and formatting checks passed; shell launchers passed `bash -n`.
- Python wheel/source distributions and all three Spec Kit archives built successfully.
- Clean Spec Kit 1.0.12 installation and coexistence with Agentstandards v0.1.1 passed.
- The built wheel's CLI was exercised outside the checkout.
- npm audit reported zero vulnerabilities after pinning image-size 2.0.4.
- All 21 slides in the three synthetic fixture decks were rendered through LibreOffice and visually
  inspected. These are output-format tests, not evidence of real GitHub acceptance.

GitHub Actions execution and protected acceptance remain unverified until repository bootstrap,
protection entitlement, pinned runner configuration, and actual human reviews are in place.
