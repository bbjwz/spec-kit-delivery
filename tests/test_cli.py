import json

from speckit_delivery.cli import main


def test_cli_plan_and_blocked_gate(project, capsys):
    root, feature = project
    args = ["--project-root", str(root), "--feature", str(feature)]
    assert main([*args, "plan", "--mapping", str(root / "mapping.json")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED" and result["baseline_hash"]
    assert main([*args, "gate", "--phase", "baseline", "--baseline-pr", "1"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
    assert main([*args, "status", "--baseline-pr", "1"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_no_guessing_between_features(project, capsys):
    root, _ = project
    second = root / "specs/002-other"
    second.mkdir()
    (second / "tasks.md").write_text("- [ ] T001 Another feature")
    assert main(["--project-root", str(root), "status", "--baseline-pr", "1"]) == 1
    assert "select the active feature" in capsys.readouterr().out
