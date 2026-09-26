from pathlib import Path
from zipfile import ZipFile

import yaml
from speckit_delivery import __version__

from scripts.build_release import build


def test_clean_archives_and_versions(tmp_path):
    root = Path(__file__).resolve().parents[1]
    files = build(tmp_path)
    assert len(files) == 3
    for file in files:
        with ZipFile(file) as archive:
            names = archive.namelist()
            assert not any("__pycache__" in name or "node_modules" in name or "/runs/" in name for name in names)
            assert not any(name.startswith("build/") or name.endswith(".pyc") for name in names)
    extension = yaml.safe_load((root / "extension.yml").read_text())
    assert extension["extension"]["version"] == __version__
    assert extension["requires"]["speckit_version"] == "==1.0.12"
    commands = {item["name"] for item in extension["provides"]["commands"]}
    assert commands == {f"speckit.delivery.{name}" for name in ("plan", "demo", "verify", "present", "status", "gate")}
    for kind, path in [("preset", "presets/delivery-gate/preset.yml"), ("workflow", "workflows/delivery/workflow.yml")]:
        assert yaml.safe_load((root / path).read_text())[kind]["version"] == __version__
