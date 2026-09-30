from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .core import (
    approval,
    inspect_status,
    load_baseline,
    make_plan,
    report_failure,
    run_demo,
    verify,
)
from .presentation import present
from .storage import feature_dir, git


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Demonstrate, verify, and present Spec Kit delivery")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--feature")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--mapping", type=Path, required=True)
    for name in ("demo", "verify", "present", "status", "gate"):
        command = commands.add_parser(name)
        command.add_argument("--baseline-pr", type=int, required=True)
        command.add_argument("--pr", type=int)
        if name == "demo":
            command.add_argument("--repair-of")
        if name == "gate":
            command.add_argument("--phase", choices=["baseline", "acceptance"], default="acceptance")
    args = parser.parse_args(argv)
    try:
        root = Path(git(args.project_root.resolve(), "rev-parse", "--show-toplevel")).resolve()
        feature = feature_dir(root, args.feature)
        if args.command == "plan":
            result = make_plan(root, feature, args.mapping)
            success = True
        elif args.command == "demo":
            result = run_demo(root, feature, args.baseline_pr, repair_of=args.repair_of)
            success = result["status"] != "BLOCKED"
        elif args.command == "present":
            result = present(root, feature, args.baseline_pr)
            success = True  # A correctly labelled blocked draft is a successful export.
        elif args.command == "gate" and args.phase == "baseline":
            result = approval(root, feature, load_baseline(feature), args.baseline_pr)
            success = True
        elif args.command == "status":
            result = inspect_status(root, feature, args.baseline_pr, args.pr)
            success = result["status"] != "BLOCKED"
        else:
            result = verify(root, feature, args.baseline_pr, pr=args.pr)
            success = result["status"] == "ACCEPTED" if args.command == "gate" else (result["status"] != "BLOCKED")
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        result = report_failure(exc)
        success = False
    print(json.dumps(result, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
