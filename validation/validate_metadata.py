#!/usr/bin/env python3
"""
Nova Rule Metadata Validator
Checks that each rule has required metadata fields with valid formats.
"""

import os
import sys
import re
import argparse
import uuid as uuid_module
from typing import Dict, Any, List, Tuple

from colorama import init as colorama_init
from nova.core.rules import NovaRule

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_utils import (
    parse_all_rules, print_pass, print_fail, print_warn, print_header,
    print_summary
)

REQUIRED_FIELDS = ["description", "author", "severity", "uuid", "date", "version", "category"]
OPTIONAL_FIELDS = ["reference", "hash", "modified"]
VALID_SEVERITIES = ["low", "medium", "high", "critical"]
CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_ ]*(/[a-z][a-z0-9_ ]*)+$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

VALID_CATEGORIES = []


def load_valid_categories() -> List[str]:
    """Load valid categories from CATEGORIES.md."""
    categories_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "CATEGORIES.md"
    )
    if not os.path.isfile(categories_file):
        return []

    categories = []
    # Pattern to match (`category/subcategory`)
    pattern = re.compile(r"\(`([a-z][a-z0-9_ ]*(/[a-z][a-z0-9_ ]*)+)`\)")
    with open(categories_file, "r") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                categories.append(match.group(1))
    return categories


def validate_uuid_v4(value: str) -> bool:
    """Validate that a string is a valid UUID v4."""
    try:
        parsed = uuid_module.UUID(value)
        return parsed.version == 4
    except (ValueError, AttributeError):
        return False


def validate_severity(value: str) -> bool:
    """Validate severity is an accepted value."""
    return value.lower() in VALID_SEVERITIES


def validate_category(value: str) -> bool:
    """Validate category format and check if it exists in CATEGORIES.md."""
    if not CATEGORY_PATTERN.match(value.lower()):
        return False
    if VALID_CATEGORIES and value.lower() not in VALID_CATEGORIES:
        return False
    return True


def validate_date(value: str) -> bool:
    """Validate date format (YYYY-MM-DD)."""
    return bool(DATE_PATTERN.match(value))


def validate_rule_metadata(
    rule: NovaRule, file_path: str
) -> Tuple[List[str], List[str]]:
    """
    Validate metadata for a single rule.
    Returns (errors, warnings).
    """
    errors = []
    warnings = []
    meta = rule.meta

    # Check for unknown fields
    allowed_fields = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    unknown_fields = set(meta.keys()) - allowed_fields
    for field in unknown_fields:
        errors.append(f"Unknown metadata field '{field}'")

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in meta or not str(meta[field]).strip():
            errors.append(f"Missing required field '{field}'")

    # Validate UUID format
    if "uuid" in meta and str(meta["uuid"]).strip():
        if not validate_uuid_v4(str(meta["uuid"])):
            errors.append(f"Invalid UUID v4 format: '{meta['uuid']}'")

    # Validate severity value
    if "severity" in meta and str(meta["severity"]).strip():
        if not validate_severity(str(meta["severity"])):
            errors.append(
                f"Invalid severity '{meta['severity']}'. "
                f"Must be one of: {', '.join(VALID_SEVERITIES)}"
            )

    # Validate category format and existence
    if "category" in meta and str(meta["category"]).strip():
        if not validate_category(str(meta["category"])):
            errors.append(
                f"Invalid category '{meta['category']}'. Must match format "
                f"'category/subcategory' and exist in CATEGORIES.md."
            )

    # Validate date format
    if "date" in meta and str(meta["date"]).strip():
        if not validate_date(str(meta["date"])):
            errors.append(f"Invalid date format: '{meta['date']}'. Use YYYY-MM-DD.")

    return errors, warnings


def run(
    rules_dir: str, verbose: bool = False, strict: bool = False, **kwargs
) -> Tuple[int, Dict[str, Any]]:
    """
    Main logic for metadata validation.
    Returns (exit_code, details_dict).
    """
    global VALID_CATEGORIES
    VALID_CATEGORIES = load_valid_categories()
    
    rules_dir = os.path.abspath(rules_dir)
    successes, parse_errors = parse_all_rules(rules_dir)

    if not successes and not parse_errors:
        print_fail(f"No .nov files found in {rules_dir}")
        return 1, {"passed": 0, "failed": 1, "warnings": 0}

    total_rules = len(successes)
    print_header(f"Metadata Validation: {total_rules} rule(s)")

    fail_messages = []
    warn_messages = []
    pass_messages = []

    if parse_errors:
        for fpath, err in parse_errors:
            relative = os.path.relpath(fpath, rules_dir)
            fail_messages.append(f"{relative}: Parse error (skipped) - {err}")

    passed = 0
    failed = 0
    warned = 0

    for fpath, rule in successes:
        relative = os.path.relpath(fpath, rules_dir)
        errors, warnings = validate_rule_metadata(rule, fpath)

        if strict:
            errors.extend(warnings)
            warnings = []

        if errors:
            failed += 1
            for e in errors:
                fail_messages.append(f"{relative} -> {rule.name}: {e}")
            for w in warnings:
                warn_messages.append(f"{relative} -> {rule.name}: {w}")
        elif warnings:
            warned += 1
            passed += 1
            if verbose:
                pass_messages.append(f"{relative} -> {rule.name}: metadata OK")
            for w in warnings:
                warn_messages.append(f"{relative} -> {rule.name}: {w}")
        else:
            passed += 1
            if verbose:
                pass_messages.append(f"{relative} -> {rule.name}: metadata OK")

    separator = f"\n{'-' * 60}"

    if fail_messages:
        print(separator)
        print(f"  {'FAILURES':^56}")
        print(f"{'-' * 60}")
        for msg in fail_messages:
            print_fail(msg)

    if warn_messages:
        print(separator)
        print(f"  {'WARNINGS':^56}")
        print(f"{'-' * 60}")
        for msg in warn_messages:
            print_warn(msg)

    if pass_messages:
        print(separator)
        print(f"  {'PASSED':^56}")
        print(f"{'-' * 60}")
        for msg in pass_messages:
            print_pass(msg)

    total_warnings = warned
    print_summary(passed, failed + len(parse_errors), total_warnings)
    exit_code = 0 if failed == 0 and len(parse_errors) == 0 else 1
    return exit_code, {"passed": passed, "failed": failed, "warnings": warned}


def main():
    parser = argparse.ArgumentParser(
        description="Validate metadata of Nova rule files."
    )
    parser.add_argument(
        "--rules-dir", default=".",
        help="Path to directory containing .nov rule files (default: current dir)"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat missing recommended fields as errors"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show per-rule success messages"
    )
    args = parser.parse_args()

    colorama_init()
    exit_code, _ = run(args.rules_dir, verbose=args.verbose, strict=args.strict)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
