# Approved implementation direction

The user approved the original Spec Kit Delivery plan in this conversation on 2026-09-26 and
changed the distribution repository from private to public on 2026-09-29. This revision records
the changed scope for review; it is not a fabricated GitHub baseline approval.

Use a deterministic Python CLI, strict versioned schemas, Git/source fingerprints, and append-only
baseline/run directories. Execute project commands with timeouts, HTTP checks with httpx, UI checks
with Playwright, and text inspections against repository files. Use a shared presentation content
model for HTML and editable PowerPoint export. Keep generated evidence outside source control.
The public source repository is a distribution channel: users clone or install the extension, while
raw CLI output, HTTP responses, screenshots, traces, speaker notes, and presentations remain local
or in explicitly configured access-controlled storage. Public CI may publish a sanitized attestation
containing hashes, identifiers, provenance, and pass/fail metadata, but no raw demonstration content.

Read human authority from live GitHub APIs and trusted default-branch policy. Separate agent
barthisagent from human approver bbjwz. Keep privileged auditing on the default branch and never
execute candidate code in that job. Use the unprivileged review event only as a wake-up signal.

Bootstrap the trust root through a separate human-reviewed PR, then pin that reviewed runner revision.
The public repository must use secret scanning, push protection, default-branch protection, and a
protected audit environment. A public evidence path fails closed when it would upload raw evidence;
trusted acceptance consumes a non-sensitive attestation and the human reviews detailed evidence
locally or through separately authorized private storage. Missing requirements keep delivery
unaccepted. No automatic merge or deployment.
