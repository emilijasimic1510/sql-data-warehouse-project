"""python -m crm_demo generate|validate|verify; standard library only."""

import argparse
import json
from pathlib import Path

from .config import DEFAULT_OUTPUT, DEFAULT_SEED, DEFAULT_START_DATE
from .generator import generate
from .validation import validate_package, verify_suite


def main(argv=None):
    parser = argparse.ArgumentParser(description="SYNTHETIC CRM DEMO ONLY; no database operations")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("generate", help="Write a new deterministic fixture directory; never overwrite")
    create.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    create.add_argument("--seed", type=int, default=DEFAULT_SEED)
    create.add_argument("--start-date", default=DEFAULT_START_DATE, help="Fixed scenario day zero, YYYY-MM-DD")
    check = commands.add_parser("validate", help="Validate one package; negative package returns exit 1")
    check.add_argument("--package-dir", type=Path, required=True)
    verify = commands.add_parser("verify", help="Verify complete generated scenario, expecting negative rejection")
    verify.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.command == "generate":
        try:
            output = generate(args.output_dir, args.seed, args.start_date)
        except (OSError, ValueError, OverflowError):
            print("Generation failed: choose a new writable, unprotected output directory and valid date parameters.")
            return 1
        print(f"Generated SYNTHETIC CRM DEMO: 7 packages in {output}")
        return 0
    result = validate_package(args.package_dir) if args.command == "validate" else verify_suite(args.output_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
