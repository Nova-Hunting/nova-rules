#!/usr/bin/env python3
"""
Shared utilities for Nova rule CI validation scripts.
Provides file discovery, rule parsing, and colored output helpers.
"""

import os
import sys
from typing import List, Tuple, Dict, Any
from colorama import Fore, Style, init as colorama_init

from nova.core.parser import NovaRuleFileParser, NovaParserError
from nova.core.rules import NovaRule


def discover_nov_files(rules_dir: str) -> List[str]:
    """
    Recursively discover all .nov files under rules_dir.
    Returns a sorted list of absolute paths.
    """
    nov_files = []
    for root, dirs, files in os.walk(rules_dir):
        # Skip hidden directories and common non-rule directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if fname.endswith('.nov'):
                nov_files.append(os.path.join(root, fname))
    return sorted(nov_files)


def parse_all_rules(rules_dir: str) -> Tuple[List[Tuple[str, NovaRule]], List[Tuple[str, str]]]:
    """
    Parse all .nov files in rules_dir using NovaRuleFileParser.
    Returns:
      - successes: List of (file_path, NovaRule) tuples
      - errors: List of (file_path, error_message) tuples
    """
    parser = NovaRuleFileParser()
    nov_files = discover_nov_files(rules_dir)
    successes = []
    errors = []

    for fpath in nov_files:
        try:
            rules = parser.parse_file(fpath)
            for rule in rules:
                successes.append((fpath, rule))
        except (NovaParserError, FileNotFoundError) as e:
            errors.append((fpath, str(e)))
        except Exception as e:
            errors.append((fpath, f"Unexpected error: {e}"))

    return successes, errors


def print_pass(msg: str) -> None:
    """Print green PASS message."""
    print(f"  {Fore.GREEN}[PASS]{Style.RESET_ALL} {msg}")


def print_fail(msg: str) -> None:
    """Print red FAIL message."""
    print(f"  {Fore.RED}[FAIL]{Style.RESET_ALL} {msg}")


def print_warn(msg: str) -> None:
    """Print yellow WARN message."""
    print(f"  {Fore.YELLOW}[WARN]{Style.RESET_ALL} {msg}")


def print_info(msg: str) -> None:
    """Print info message."""
    print(f"  [INFO] {msg}")


def print_header(title: str) -> None:
    """Print section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_summary(passed: int, failed: int, third: int, third_label: str = "warnings") -> None:
    """Print final summary with counts and color-coded status."""
    print(f"\n{'-' * 60}")
    parts = [f"{Fore.GREEN}{passed} passed{Style.RESET_ALL}"]
    if failed > 0:
        parts.append(f"{Fore.RED}{failed} failed{Style.RESET_ALL}")
    else:
        parts.append(f"{failed} failed")
    if third > 0:
        parts.append(f"{Fore.YELLOW}{third} {third_label}{Style.RESET_ALL}")
    else:
        parts.append(f"{third} {third_label}")
    print(f"  Summary: {', '.join(parts)}")

    if failed > 0:
        print(f"  Status: {Fore.RED}FAILED{Style.RESET_ALL}")
    elif third > 0:
        print(f"  Status: {Fore.GREEN}PASSED{Style.RESET_ALL} (with {third_label})")
    else:
        print(f"  Status: {Fore.GREEN}PASSED{Style.RESET_ALL}")
