from __future__ import annotations

import html
import json
import subprocess
import textwrap
from pathlib import Path

from .core import current_run, load_baseline, verify
from .storage import digest, file_hash, inside, write


def chunks(text: str, width: int = 420):
    return textwrap.wrap(text, width, break_long_words=True, replace_whitespace=False) or [""]


def content(root, feature, baseline_pr, github=None) -> dict:
    baseline = load_baseline(feature)
    folder, run = current_run(feature)
    report = verify(root, feature, baseline_pr, github=github, require_presentations=False)
    narrative = baseline.narrative
    results = {r["id"]: r for r in run["records"]}
    common = [
        {
            "title": baseline.title,
            "body": [narrative.problem],
            "notes": "Introduce the problem and the approved scope. " + report["status"],
        },
        {
            "title": "Delivery status",
            "body": [
                f"{report['status']}: {sum(bool(r.get('passed')) for r in results.values())} / "
                f"{len(baseline.scenarios)} recorded scenarios passed.",
                "Human acceptance is a separate GitHub decision for the verified revision.",
                *report["errors"],
            ],
            "notes": "Do not describe a draft or blocked feature as accepted.",
        },
    ]
    limitations = narrative.limitations + report["errors"]
    closing = [
        {
            "title": "Limitations and decisions",
            "body": limitations or ["No additional limitations were recorded; human review is still required."],
            "notes": "Discuss evidence limits, operational dependencies, and the acceptance decision.",
        },
        {
            "title": "Human acceptance",
            "body": [
                "Review the demonstrated behavior and evidence package before accepting the PR.",
                "Merging and deployment are separate decisions.",
            ],
            "notes": "The CLI prints the exact evidence digest to include in the GitHub review.",
        },
    ]
    demos = []
    technical = []
    for scenario in baseline.scenarios:
        record = results.get(scenario.id, {})
        evidence = f"../runs/{run['run_id']}/{scenario.id}/result.json"
        slide = {
            "title": scenario.title,
            "body": [
                scenario.expected,
                f"Observed: {'PASS' if record.get('passed') else 'FAIL'}",
                "Covers: " + ", ".join(scenario.obligations),
            ],
            "evidence": evidence,
            "notes": f"Scenario {scenario.id}. Reproduce using the runbook. Evidence: {evidence}",
        }
        screenshot = folder / scenario.id / "screenshot.png"
        demos.append(slide)
        if screenshot.exists():
            demos.append(
                {
                    "title": f"Demonstration: {scenario.title}",
                    "body": ["Captured execution evidence"],
                    "image": f"../runs/{run['run_id']}/{scenario.id}/screenshot.png",
                    "evidence": evidence,
                    "notes": slide["notes"],
                }
            )
        technical.append(
            {
                "title": f"Verification: {scenario.id}",
                "body": [
                    f"Method: {scenario.kind}; timeout: {scenario.timeout_seconds}s",
                    "Assertions: "
                    + "; ".join(f"{a.field} {a.operator} {json.dumps(a.value)}" for a in scenario.assertions)
                    if scenario.assertions
                    else "Assertions: "
                    + "; ".join(
                        f"{step.action} {step.target} {step.value}"
                        for step in scenario.steps
                        if step.action.startswith("assert_")
                    ),
                    "Failure: " + record.get("error", "None recorded"),
                ],
                "evidence": evidence,
                "notes": json.dumps(record, indent=2),
            }
        )
    decks = {
        "L0": common
        + [
            {
                "title": "Expected benefit",
                "body": [
                    narrative.expected_benefit,
                    "Business impact is not measured by technical test success.",
                ],
                "notes": "Label benefits as expectations unless measured evidence is supplied.",
            }
        ]
        + demos[:1]
        + closing,
        "L1": common + demos + closing,
        "L2": common
        + [
            {
                "title": "Implementation",
                "body": [narrative.implementation],
                "notes": "Connect design choices to the approved plan.",
            }
        ]
        + technical
        + [
            {
                "title": "Operations and recovery",
                "body": [
                    narrative.operations,
                    f"Repair cycle: {run['repair_cycle']} of 3; failed attempts remain in runs/.",
                ],
                "notes": "Review rollout and recovery before deployment.",
            }
        ]
        + closing,
    }
    # Paginate rather than shrinking text or silently truncating obligations.
    for level, slides in decks.items():
        paginated = []
        for slide in slides:
            lines = [part for body in slide["body"] for part in chunks(body, 180)]
            capacity = 2 if slide.get("image") else 4
            for offset in range(0, len(lines), capacity):
                page = dict(slide, body=lines[offset : offset + capacity])
                page["notes"] += (
                    f"\nEvidence revision: {run['revision']}"
                    f"\nRun: {run['run_id']}\nSource fingerprint: {run['source_hash']}"
                )
                if offset:
                    page["title"] += " (continued)"
                paginated.append(page)
        decks[level] = paginated
    return {
        "schema_version": 1,
        "title": baseline.title,
        "brand": narrative.brand,
        "accent": narrative.accent,
        "status": report["status"],
        "run_hash": digest(run),
        "baseline_hash": digest(baseline.model_dump(mode="json")),
        "decks": decks,
    }


def render_html(deck: dict, level: str) -> str:
    esc = html.escape
    slides = []
    for index, slide in enumerate(deck["decks"][level]):
        image = (
            f'<img src="{esc(slide["image"], quote=True)}" alt="Captured demonstration"/>' if slide.get("image") else ""
        )
        link = f'<a href="{esc(slide["evidence"], quote=True)}">Execution evidence</a>' if slide.get("evidence") else ""
        slides.append(
            f'<section id="slide-{index + 1}"><header>{esc(deck["brand"])} · {level}'
            f" · {esc(deck['status'])}</header><h1>{esc(slide['title'])}</h1>"
            + "".join(f"<p>{esc(line)}</p>" for line in slide["body"])
            + image
            + link
            + f"<details><summary>Speaker notes</summary>"
            f"<pre>{esc(slide['notes'])}</pre></details></section>"
        )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(deck["title"])} — {level}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#e7edf0;font-family:Arial,sans-serif;color:#172f3c}}
section{{background:white;max-width:1280px;min-height:720px;padding:48px 64px;margin:28px auto}}
header{{color:{deck["accent"]};font-size:17px}}h1{{font-size:42px;line-height:1.15;margin:32px 0}}
p{{font-size:25px;line-height:1.45;overflow-wrap:anywhere}}img{{max-width:100%;max-height:330px}}
a{{color:{deck["accent"]}}}details{{margin-top:24px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
nav{{position:sticky;top:0;background:#172f3c;padding:12px;color:white}}button{{font-size:18px;margin:0 8px}}
@media print{{nav,details{{display:none}}section{{break-after:page;margin:0}}}}
</style><nav><button id="prev">Previous</button><button id="next">Next</button>
Arrow keys navigate · {level}</nav>{"".join(slides)}<script>
let current=0;const slides=[...document.querySelectorAll('section')];
function move(n){{current=Math.max(0,Math.min(slides.length-1,current+n));slides[current].scrollIntoView();}}
document.getElementById('prev').onclick=()=>move(-1);document.getElementById('next').onclick=()=>move(1);
document.onkeydown=e=>{{if(e.key==='ArrowRight')move(1);if(e.key==='ArrowLeft')move(-1);}};
</script></html>"""


def present(root: Path, feature: Path, baseline_pr: int, github=None) -> dict:
    data = content(root, feature, baseline_pr, github)
    output = inside(root, feature / "delivery/presentations")
    output.mkdir(parents=True, exist_ok=True)
    # Remove the validity marker first; failed export must never retain an old valid package.
    (output / "manifest.json").unlink(missing_ok=True)
    write(output / "content.json", data)
    for level in data["decks"]:
        (output / f"{level}.html").write_text(render_html(data, level))
    script = Path(__file__).parent / "render-pptx.mjs"
    result = subprocess.run(["node", str(script), str(output)], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError("PowerPoint export failed; run npm ci in the extension: " + result.stderr)
    baseline = load_baseline(feature)
    _, run = current_run(feature)
    runbook = [
        f"# {baseline.title}: demonstration runbook",
        "",
        f"Captured revision: {run['revision']}; run: {run['run_id']}",
        f"Source fingerprint: {run['source_hash']}",
        "",
        "Use synthetic test data. Run against the environment approved in the baseline.",
        "Repeat all scenarios with `speckit-delivery demo --baseline-pr <number>`.",
        "If live execution is unavailable, show captured evidence and disclose its revision.",
        "",
    ]
    for scenario in baseline.scenarios:
        runbook += [
            f"## {scenario.id}: {scenario.title}",
            scenario.expected,
            "```json",
            json.dumps(scenario.model_dump(mode="json"), indent=2),
            "```",
            "",
        ]
    (output / "runbook.md").write_text("\n".join(runbook))
    manifest = {
        "schema_version": 1,
        "run_hash": data["run_hash"],
        "baseline_hash": data["baseline_hash"],
        "artifacts": {
            p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"
        },
    }
    write(output / "manifest.json", manifest)
    return {"status": data["status"], "directory": str(output), "artifacts": manifest["artifacts"]}
