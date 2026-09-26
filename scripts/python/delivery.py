# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.10,<3", "PyYAML>=6,<7", "httpx>=0.28,<1", "playwright>=1.51,<2"]
# ///
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))
from speckit_delivery.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
