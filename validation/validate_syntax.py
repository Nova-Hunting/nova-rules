#!/usr/bin/env python3
"""
Nova Rule Syntax Validator
Discovers all .nov files and validates their syntax using the Nova parser.
"""

import os
import sys
import argparse
from typing import Dict, Any, Tuple

from colorama import init as colorama_init
from nova.core.parser import NovaRuleFileParser, NovaParserError

# Allow imports from the validation package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_utils import (
    discover_nov_files, print_pass, print_fail, print_header, print_summary
)


def run(rules_dir: str, verbose: bool = False, **kwargs) -> Tuple[int, Dict[str, Any]]:
    """
    Main logic for syntax validation.
    Returns (exit_code, details_dict).
    """
    rules_dir = os.path.abspath(rules_dir)
    if not os.path.isdir(rules_dir):
        print_fail(f"Rules directory not found: {rules_dir}")
        return 1, {"passed": 0, "failed": 1}

    nov_files = discover_nov_files(rules_dir)
    if not nov_files:
        print_fail(f"No .nov files found in {rules_dir}")
        return 1, {"passed": 0, "failed": 1}

    print_header(f"Syntax Validation: {len(nov_files)} file(s)")

    parser = NovaRuleFileParser()
    passed = 0
    failed = 0

    for fpath in nov_files:
        relative = os.path.relpath(fpath, rules_dir)
        try:
            rules = parser.parse_file(fpath)
            passed += 1
            if verbose:
                print_pass(f"{relative}: {len(rules)} rule(s) parsed OK")
        except NovaParserError as e:
            failed += 1
            print_fail(f"{relative}: {e}")
        except Exception as e:
            failed += 1
            print_fail(f"{relative}: Unexpected error: {e}")

    print_summary(passed, failed, 0)
    exit_code = 0 if failed == 0 else 1
    return exit_code, {"passed": passed, "failed": failed}


def main():
    parser = argparse.ArgumentParser(
        description="Validate syntax of Nova rule files."
    )
    parser.add_argument(
        "--rules-dir", default=".",
        help="Path to directory containing .nov rule files (default: current dir)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show per-file success messages"
    )
    args = parser.parse_args()

    colorama_init()
    exit_code, _ = run(args.rules_dir, verbose=args.verbose)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
