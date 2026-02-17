#!/usr/bin/env python3
"""
Nova Rule Linter
Cross-file checks for consistency, naming conventions, duplicates,
and structural quality issues.
"""

import os
import sys
import re
import argparse
from typing import Dict, Any, List, Tuple

from colorama import init as colorama_init
from nova.core.rules import NovaRule

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_utils import (
    discover_nov_files, parse_all_rules,
    print_pass, print_fail, print_warn, print_header, print_summary
)

PASCAL_CASE_PATTERN = re.compile(r"^[A-Z][a-zA-Z0-9]*$")


def check_duplicate_uuids(
    rules_with_files: List[Tuple[str, NovaRule]], rules_dir: str
) -> List[str]:
    """Check for duplicate UUIDs across all rules. Returns error messages."""
    uuid_map: Dict[str, List[Tuple[str, str]]] = {}
    errors = []

    for fpath, rule in rules_with_files:
        rule_uuid = rule.meta.get("uuid", "").strip()
        if not rule_uuid:
            continue
        if rule_uuid in uuid_map:
            existing_file, existing_name = uuid_map[rule_uuid][0]
            errors.append(
                f"Duplicate UUID '{rule_uuid}': "
                f"'{rule.name}' in {os.path.relpath(fpath, rules_dir)} and "
                f"'{existing_name}' in {os.path.relpath(existing_file, rules_dir)}"
            )
            uuid_map[rule_uuid].append((fpath, rule.name))
        else:
            uuid_map[rule_uuid] = [(fpath, rule.name)]

    return errors


def check_duplicate_rule_names(
    rules_with_files: List[Tuple[str, NovaRule]], rules_dir: str
) -> List[str]:
    """Check for duplicate rule names across all files. Returns error messages."""
    name_map: Dict[str, List[str]] = {}
    errors = []

    for fpath, rule in rules_with_files:
        relative = os.path.relpath(fpath, rules_dir)
        if rule.name in name_map:
            errors.append(
                f"Duplicate rule name '{rule.name}': "
                f"found in {relative} and {name_map[rule.name][0]}"
            )
            name_map[rule.name].append(relative)
        else:
            name_map[rule.name] = [relative]

    return errors


def check_naming_convention(
    rules_with_files: List[Tuple[str, NovaRule]], rules_dir: str
) -> List[str]:
    """Check that rule names follow PascalCase convention. Returns warnings."""
    warnings = []
    for fpath, rule in rules_with_files:
        relative = os.path.relpath(fpath, rules_dir)
        if not PASCAL_CASE_PATTERN.match(rule.name):
            warnings.append(
                f"Rule '{rule.name}' in {relative}: "
                f"name does not follow PascalCase convention"
            )
    return warnings


def check_file_extensions(nov_files: List[str], rules_dir: str) -> List[str]:
    """Warn about rule-like files with non-standard extensions.
    Checks sibling files in directories that contain .nov files."""
    warnings = []
    checked_dirs = set()
    for nov_path in nov_files:
        parent = os.path.dirname(nov_path)
        if parent in checked_dirs:
            continue
        checked_dirs.add(parent)
        for fname in os.listdir(parent):
            if fname.endswith((".nova", ".rule", ".yar", ".yara")):
                fpath = os.path.join(parent, fname)
                relative = os.path.relpath(fpath, rules_dir)
                warnings.append(
                    f"File '{relative}': non-standard extension. Use .nov instead."
                )
    return warnings


def check_expensive_rules(
    rules_with_files: List[Tuple[str, NovaRule]], rules_dir: str
) -> List[str]:
    """Warn about rules that have no keyword patterns (expensive to evaluate)."""
    warnings = []
    for fpath, rule in rules_with_files:
        relative = os.path.relpath(fpath, rules_dir)
        if not rule.keywords and (rule.semantics or rule.llms):
            types = []
            if rule.semantics:
                types.append("semantics")
            if rule.llms:
                types.append("llm")
            warnings.append(
                f"Rule '{rule.name}' in {relative}: "
                f"no keyword patterns. Uses only {', '.join(types)}. "
                f"Consider adding keyword pre-filters for performance."
            )
    return warnings


def run(rules_dir: str, verbose: bool = False, **kwargs) -> Tuple[int, Dict[str, Any]]:
    """
    Main logic for linting.
    Returns (exit_code, details_dict).
    """
    rules_dir = os.path.abspath(rules_dir)
    nov_files = discover_nov_files(rules_dir)
    successes, parse_errors = parse_all_rules(rules_dir)

    if not successes and not parse_errors:
        print_fail(f"No .nov files found in {rules_dir}")
        return 1, {"errors": 1, "warnings": 0}

    total_rules = len(successes)
    print_header(f"Lint Check: {total_rules} rule(s)")

    all_errors = []
    all_warnings = []

    # --- Error checks ---
    print(f"\n  --- Duplicate UUIDs ---")
    dup_uuids = check_duplicate_uuids(successes, rules_dir)
    if dup_uuids:
        all_errors.extend(dup_uuids)
        for e in dup_uuids:
            print_fail(e)
    else:
        print_pass("No duplicate UUIDs found")

    print(f"\n  --- Duplicate Rule Names ---")
    dup_names = check_duplicate_rule_names(successes, rules_dir)
    if dup_names:
        all_errors.extend(dup_names)
        for e in dup_names:
            print_fail(e)
    else:
        print_pass("No duplicate rule names found")

    # --- Warning checks ---
    print(f"\n  --- Naming Conventions ---")
    naming_warnings = check_naming_convention(successes, rules_dir)
    if naming_warnings:
        all_warnings.extend(naming_warnings)
        for w in naming_warnings:
            print_warn(w)
    else:
        print_pass("All rule names follow PascalCase")

    print(f"\n  --- File Extensions ---")
    ext_warnings = check_file_extensions(nov_files, rules_dir)
    if ext_warnings:
        all_warnings.extend(ext_warnings)
        for w in ext_warnings:
            print_warn(w)
    else:
        print_pass("All rule files use .nov extension")

    print(f"\n  --- Expensive Rules (no keywords) ---")
    expensive_warnings = check_expensive_rules(successes, rules_dir)
    if expensive_warnings:
        all_warnings.extend(expensive_warnings)
        for w in expensive_warnings:
            print_warn(w)
    else:
        print_pass("All rules have keyword patterns")

    error_count = len(all_errors)
    warn_count = len(all_warnings)
    passed_count = total_rules - error_count
    print_summary(passed_count if passed_count > 0 else 0, error_count, warn_count)

    exit_code = 0 if error_count == 0 else 1
    return exit_code, {"errors": error_count, "warnings": warn_count}


def main():
    parser = argparse.ArgumentParser(
        description="Lint Nova rule files for consistency and best practices."
    )
    parser.add_argument(
        "--rules-dir", default=".",
        help="Path to directory containing .nov rule files (default: current dir)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show detailed output"
    )
    args = parser.parse_args()

    colorama_init()
    exit_code, _ = run(args.rules_dir, verbose=args.verbose)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
