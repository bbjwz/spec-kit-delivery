## Delivery prerequisite

Run `$speckit-delivery-gate` in baseline mode before changing implementation files.
Use the approved baseline PR number. If the gate fails, stop and show the reason.
Never substitute local approval text for a GitHub review.

{CORE_TEMPLATE}

## Delivery completion contract

Task checkboxes record implementation progress only. They do not mean delivery acceptance.
Run `$speckit-delivery-demo`, `$speckit-delivery-present`, and `$speckit-delivery-verify`.
If demonstrations fail, fix only within approved scope, then rerun all scenarios and regression
checks. At most three repair cycles are permitted; preserve every failed attempt. Do not reset
run history to avoid the limit. Changes to obligations require a revised, human-approved baseline.
Report BLOCKED or READY_FOR_REVIEW. Claim ACCEPTED only when the acceptance gate reads a current
human GitHub approval and passing trusted CI for the verified revision. Never approve as the human.
