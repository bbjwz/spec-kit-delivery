# Spec Kit Delivery

Public development repository for an independent Spec Kit extension that demonstrates, verifies,
and presents completed work.

This bootstrap establishes the trusted verifier used by delivery workflows. It executes approved
scenarios in an unprivileged pull-request job and validates raw evidence inside that ephemeral runner.
The only public artifact is `attestation.json`, an allowlisted record of revision IDs, baseline and
evidence hashes, scenario and obligation pass/fail state, and approval provenance.

Raw command output, HTTP response bodies, screenshots, browser traces, speaker notes, and generated
presentations are never uploaded by the public workflow. Review those materials locally or place them
in a separately configured private evidence store. The workflow deletes them from the candidate
checkout after producing the attestation.

The trusted revision is configured through `DELIVERY_RUNNER_SHA`. Final acceptance additionally
requires protected-branch settings, the `delivery-audit` environment, a successful attestation for
the current PR revision, and a distinct human approval bound to the evidence digest.
