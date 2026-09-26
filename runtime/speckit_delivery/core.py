from __future__ import annotations

import json
import platform
import re
import uuid
from pathlib import Path

from . import __version__
from .adapters import execute
from .github import GitHub, github_for
from .models import Baseline
from .storage import digest, documents, file_hash, git, inside, now, read, source_manifest, write


def runner_hash() -> str:
    module = Path(__file__).parent
    files = {p.name: file_hash(p) for p in module.iterdir() if p.suffix in {".py", ".mjs"}}
    lock = module / "package-lock.json"
    if not lock.exists():
        lock = module.parents[1] / "package-lock.json"
    if lock.exists():
        files["package-lock.json"] = file_hash(lock)
    return digest(files)


def baseline_file(feature: Path) -> Path:
    return feature / "delivery/baseline.json"


def load_baseline(feature: Path) -> Baseline:
    path = inside(feature, "delivery/baseline.json")
    baseline = Baseline.model_validate(read(path))
    if baseline.documents != documents(feature):
        raise ValueError("specification, plan, or tasks changed; prepare a revised baseline")
    return baseline


def task_ids(text: str) -> set[str]:
    ids = re.findall(r"(?m)^\s*- \[[ xX]\]\s+(T\d+)\b", text)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task IDs in tasks.md")
    return set(ids)


def check_mapping(baseline: Baseline) -> None:
    mapped = {o.id for o in baseline.obligations if o.kind == "task"}
    if mapped != task_ids(baseline.documents["tasks.md"]):
        raise ValueError("every tasks.md task must have exactly one matching task obligation")
    for kind in ("requirement", "acceptance"):
        if not any(o.kind == kind for o in baseline.obligations):
            raise ValueError(f"baseline requires explicit {kind} obligations")
    for obligation in baseline.obligations:
        if obligation.source not in baseline.documents:
            raise ValueError(f"unknown obligation source: {obligation.source}")


def make_plan(root: Path, feature: Path, mapping: Path) -> dict:
    raw = read(mapping)
    raw["documents"] = documents(feature)
    baseline = Baseline.model_validate(raw)
    check_mapping(baseline)
    path = inside(root, baseline_file(feature))
    content = baseline.model_dump(mode="json")
    if path.exists():
        old = read(path)
        history = inside(root, feature / "delivery/baselines" / f"{digest(old)}.json")
        write(history, old)
    ignore = inside(root, feature / "delivery/.gitignore")
    if not ignore.exists():
        ignore.parent.mkdir(parents=True, exist_ok=True)
        ignore.write_text("runs/\npresentations/\nverification.json\n")
    write(path, content)
    write(inside(root, feature / "delivery/baselines" / f"{digest(content)}.json"), content)
    return {
        "baseline": str(path),
        "baseline_hash": digest(content),
        "approval_instruction": f"Human GitHub review body: delivery-baseline: {digest(content)}",
        "status": "BLOCKED",
        "reason": "baseline requires human GitHub approval",
    }


def approval(root: Path, feature: Path, baseline: Baseline, pr: int, github: GitHub | None = None) -> dict:
    if not pr:
        raise ValueError("--baseline-pr is required for human baseline approval")
    gh = github or github_for(root)
    return gh.baseline_approval(
        pr, str(baseline_file(feature).relative_to(root)), digest(baseline.model_dump(mode="json"))
    )


def run_demo(
    root: Path,
    feature: Path,
    baseline_pr: int,
    *,
    repair_of: str | None = None,
    github: GitHub | None = None,
) -> dict:
    baseline = load_baseline(feature)
    check_mapping(baseline)
    receipt = approval(root, feature, baseline, baseline_pr, github)
    baseline_hash = digest(baseline.model_dump(mode="json"))
    cycle = 0
    latest_pointer = feature / "delivery/runs/latest.json"
    if latest_pointer.exists():
        _, previous = current_run(feature)
        if previous["baseline_hash"] == baseline_hash and previous["status"] == "BLOCKED":
            if repair_of and repair_of != previous["run_id"]:
                raise ValueError("repair must continue the latest failed attempt")
            repair_of = previous["run_id"]
    if repair_of:
        if not re.fullmatch(r"[0-9a-f]{32}", repair_of):
            raise ValueError("invalid repair run ID")
        prior = read(inside(feature, f"delivery/runs/{repair_of}/run.json"))
        if prior["baseline_hash"] != baseline_hash:
            raise ValueError("repairs cannot change approved scope")
        if prior["status"] != "BLOCKED":
            raise ValueError("repair parent must be a failed run")
        cycle = prior["repair_cycle"] + 1
        if cycle > 3:
            raise ValueError("three repair cycles exhausted; human direction required")
    run_id = uuid.uuid4().hex
    output = inside(root, feature / "delivery/runs" / run_id)
    output.mkdir(parents=True)
    started = now()
    manifest = source_manifest(root)
    records = []
    for scenario in baseline.scenarios:
        folder = inside(output, scenario.id)
        folder.mkdir()
        record = {
            "id": scenario.id,
            "scenario_hash": digest(scenario.model_dump(mode="json")),
            "obligations": scenario.obligations,
            "expected": scenario.expected,
            "started_at": now(),
        }
        try:
            observed, checks = execute(scenario, root, folder)
            passed = bool(checks) and all(c["passed"] for c in checks)
            if observed.get("timeout"):
                passed = False
            record.update(observed=observed, assertions=checks, passed=passed)
        except Exception as exc:
            record.update(observed={}, assertions=[], passed=False, error=f"{type(exc).__name__}: {exc}")
        record["finished_at"] = now()
        write(folder / "result.json", record)
        records.append(record)
    artifacts = {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob("*")) if p.is_file()}
    unchanged = source_manifest(root) == manifest
    run = {
        "schema_version": 1,
        "run_id": run_id,
        "baseline_hash": baseline_hash,
        "baseline_pr": baseline_pr,
        "baseline_approval": receipt,
        "source_manifest": manifest,
        "source_hash": digest(manifest),
        "revision": git(root, "rev-parse", "HEAD"),
        "started_at": started,
        "finished_at": now(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "runner_version": __version__,
            "runner_hash": runner_hash(),
        },
        "repair_cycle": cycle,
        "repair_of": repair_of,
        "source_unchanged": unchanged,
        "records": records,
        "artifacts": artifacts,
        "status": "READY_FOR_REVIEW" if unchanged and all(r["passed"] for r in records) else "BLOCKED",
    }
    write(output / "run.json", run)
    write(inside(feature, "delivery/runs/latest.json"), {"run_id": run_id})
    return run


def current_run(feature: Path) -> tuple[Path, dict]:
    pointer = read(inside(feature, "delivery/runs/latest.json"))
    run_id = pointer["run_id"]
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("invalid evidence run pointer")
    folder = inside(feature, f"delivery/runs/{run_id}")
    return folder, read(inside(folder, "run.json"))


def verify(
    root: Path,
    feature: Path,
    baseline_pr: int,
    *,
    pr: int | None = None,
    github: GitHub | None = None,
    require_presentations: bool = True,
) -> dict:
    errors = []
    baseline = load_baseline(feature)
    check_mapping(baseline)
    folder, run = current_run(feature)
    baseline_hash = digest(baseline.model_dump(mode="json"))
    if run["environment"].get("runner_hash") != runner_hash():
        errors.append("verification runner changed; evidence is stale")
    if run["baseline_hash"] != baseline_hash:
        errors.append("evidence belongs to a different baseline")
    if run["source_manifest"] != source_manifest(root) or not run["source_unchanged"]:
        errors.append("source changed; evidence is stale")
    if run["source_hash"] != digest(run["source_manifest"]):
        errors.append("source fingerprint mismatch")
    if run["baseline_pr"] != baseline_pr:
        errors.append("evidence baseline review does not match the selected baseline PR")
    expected = {s.id: s for s in baseline.scenarios}
    ids = [record["id"] for record in run["records"]]
    if set(ids) != set(expected) or len(ids) != len(set(ids)):
        errors.append("missing, duplicate, or unknown scenario results")
    for record in run["records"]:
        scenario = expected.get(record["id"])
        if not scenario:
            continue
        result_path = f"{scenario.id}/result.json"
        if result_path not in run["artifacts"]:
            errors.append(f"missing result artifact: {scenario.id}")
        else:
            if read(inside(folder, result_path)) != record:
                errors.append(f"result manifest mismatch: {scenario.id}")
        if record["scenario_hash"] != digest(scenario.model_dump(mode="json")):
            errors.append(f"scenario definition changed: {scenario.id}")
        if record["obligations"] != scenario.obligations:
            errors.append(f"obligation mapping changed: {scenario.id}")
        if not record.get("passed") or not record.get("assertions"):
            errors.append(f"scenario did not pass: {scenario.id}")
        elif scenario.kind != "ui":
            from .adapters import assert_values

            checks = assert_values(record["observed"], scenario.assertions)
            if checks != record["assertions"] or not all(c["passed"] for c in checks):
                errors.append(f"assertions do not match observations: {scenario.id}")
        else:
            needed = [s.model_dump() for s in scenario.steps if s.action.startswith("assert_")]
            actual = [c.get("assertion") for c in record["assertions"] if c.get("passed")]
            if actual != needed or any(not c["passed"] for c in record["assertions"]):
                errors.append(f"UI assertions missing or failed: {scenario.id}")
            for suffix in ("screenshot.png", "trace.zip"):
                if f"{scenario.id}/{suffix}" not in run["artifacts"]:
                    errors.append(f"missing UI evidence: {scenario.id}/{suffix}")
    for name, checksum in run["artifacts"].items():
        path = inside(folder, name)
        if not path.is_file() or file_hash(path) != checksum:
            errors.append(f"missing or altered artifact: {name}")
    if require_presentations:
        try:
            package = read(inside(feature, "delivery/presentations/manifest.json"))
            if package["run_hash"] != digest(run):
                errors.append("presentations refer to a different evidence run")
            if package["baseline_hash"] != baseline_hash:
                errors.append("presentations refer to a different baseline")
            required = {f"{level}.{ext}" for level in ("L0", "L1", "L2") for ext in ("html", "pptx")}
            if not required.issubset(package["artifacts"]):
                errors.append("browser and PowerPoint decks are required for all levels")
            for name, checksum in package["artifacts"].items():
                path = inside(feature, f"delivery/presentations/{name}")
                if not path.is_file() or file_hash(path) != checksum:
                    errors.append(f"missing or altered presentation: {name}")
        except (OSError, KeyError, TypeError):
            errors.append("presentation package is missing or incomplete")
            package = {}
    else:
        package = {}
    try:
        current_approval = approval(root, feature, baseline, baseline_pr, github)
        if run["baseline_approval"] != current_approval:
            errors.append("baseline approval changed; rerun evidence after the current approval")
    except (ValueError, OSError, KeyError) as exc:
        errors.append(str(exc))
    evidence_hash = digest({"run": digest(run), "presentations": package})
    status = "BLOCKED" if errors else "READY_FOR_REVIEW"
    acceptance = None
    acceptance_blockers = []
    if not errors and pr:
        try:
            if git(root, "status", "--porcelain", "--untracked-files=normal"):
                raise ValueError("human acceptance requires a clean committed checkout")
            acceptance = (github or github_for(root)).final_approval(pr, git(root, "rev-parse", "HEAD"), evidence_hash)
            status = "ACCEPTED"
        except (ValueError, OSError, KeyError) as exc:
            acceptance_blockers.append(str(exc))
    elif not errors:
        acceptance_blockers.append("human GitHub acceptance has not been checked; provide --pr")
    report = {
        "schema_version": 1,
        "status": status,
        "errors": errors,
        "acceptance_blockers": acceptance_blockers,
        "acceptance": acceptance,
        "run_id": run["run_id"],
        "evidence_hash": evidence_hash,
        "approval_instruction": f"Human GitHub review body: delivery-accept: {evidence_hash}",
    }
    write(inside(feature, "delivery/verification.json"), report)
    return report


def report_failure(exc: Exception) -> dict:
    return {"status": "BLOCKED", "errors": [f"{type(exc).__name__}: {exc}"]}


def inspect_status(root: Path, feature: Path, baseline_pr: int, pr: int | None = None) -> dict:
    try:
        return verify(root, feature, baseline_pr, pr=pr)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return report_failure(exc)
