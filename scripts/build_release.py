"""Build reviewed-source-only Spec Kit distributions; never package working artifacts."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    groups = {
        "delivery-0.1.0.zip": [
            "extension.yml",
            "README.md",
            "LICENSE",
            "package.json",
            "package-lock.json",
            "commands",
            "runtime",
            "scripts/python",
            "scripts/bash",
            "scripts/powershell",
            "examples",
        ],
        "delivery-gate-0.1.0.zip": ["presets/delivery-gate"],
        "delivery-workflow-0.1.0.zip": ["workflows/delivery"],
    }
    for name, entries in groups.items():
        with ZipFile(output / name, "w", ZIP_DEFLATED) as archive:
            for entry in entries:
                source = ROOT / entry
                paths = source.rglob("*") if source.is_dir() else [source]
                for path in sorted(paths):
                    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                        base = ROOT
                        if name.startswith("delivery-gate"):
                            base = ROOT / "presets/delivery-gate"
                        elif name.startswith("delivery-workflow"):
                            base = ROOT / "workflows/delivery"
                        archive.write(path, path.relative_to(base))
    return sorted(output.glob("*.zip"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist/spec-kit")
    args = parser.parse_args()
    for archive in build(args.output):
        print(archive)
