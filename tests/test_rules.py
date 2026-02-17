#!/usr/bin/env python3
"""
Nova Rule Test Runner

This script is the primary tool for functionally testing Nova rules. It is designed to
be run from the command line and offers a flexible way to validate the behavior of
rules against a set of predefined test cases.

The script works by loading test cases from YAML files located in the `tests/`
directory. Each test case defines a prompt and an expected outcome (i.e., whether
a rule should match or not). The script then runs the Nova matching engine against
each prompt and compares the actual outcome with the expected one.

The test runner supports three types of matching:
- **Keyword Matching**: The default and most common type of matching.
- **Semantic Matching**: For rules that use semantic vectors for matching.
- **LLM-based Matching**: For rules that require a Large Language Model for
  evaluation. This is an optional feature that can be enabled via the
  command line.

By default, LLM-based evaluation is skipped to avoid the need for API keys in
CI/CD environments. To enable it, use the `--llm-testing` flag and specify an
LLM provider with `--llm-provider`.
"""

import os
import sys
import re
import copy
import argparse
from typing import Dict, Any, List, Tuple, Optional

import yaml
from colorama import init as colorama_init
from nova.core.parser import NovaRuleFileParser, NovaParserError
from nova.core.matcher import NovaMatcher
from nova.core.rules import NovaRule
from nova.evaluators.base import LLMEvaluator
from nova.evaluators.semantics import DefaultSemanticEvaluator
from nova.evaluators.llm import get_validated_evaluator

# Allow imports from sibling validation package
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "validation"))
from ci_utils import print_pass, print_fail, print_warn, print_header, print_summary

# Shared semantic evaluator instance (loaded once, reused across all tests)
_semantic_evaluator = None
_llm_evaluator = None


def get_semantic_evaluator() -> DefaultSemanticEvaluator:
    """Lazy-load and return a shared semantic evaluator."""
    global _semantic_evaluator
    if _semantic_evaluator is None:
        _semantic_evaluator = DefaultSemanticEvaluator()
    return _semantic_evaluator


def needs_llm(rule: NovaRule) -> bool:
    """Check if a rule's condition requires LLM evaluation to ever match."""
    condition = rule.condition.lower()
    if "llm." in condition:
        return True
    for match in re.finditer(r"\$([a-zA-Z0-9_]+)", condition):
        var_name = "$" + match.group(1)
        if var_name in (rule.llms or {}):
            return True
    return False


def load_test_cases(tests_dir: str) -> List[Dict[str, Any]]:
    """
    Load all YAML test case files from tests_dir.
    Returns flat list of test case dicts with source metadata added.

    Supports both single ``prompt`` and multi ``prompts`` formats.
    A test with ``prompts: [p1, p2]`` is expanded into separate test
    cases named "<name> [1/2]", "<name> [2/2]".
    """
    test_cases = []
    for root, dirs, files in os.walk(tests_dir):
        for fname in sorted(files):
            if fname.endswith((".yaml", ".yml")) and not fname.startswith("."):
                fpath = os.path.join(root, fname)
                with open(fpath, "r") as f:
                    data = yaml.safe_load(f)
                if data and "tests" in data:
                    for tc in data["tests"]:
                        tc["_source_yaml"] = fpath
                        tc["_rule_file"] = data.get("rule_file", "")
                        if "rule_name" not in tc:
                            tc["rule_name"] = data.get("rule_name", "")

                        # Expand multi-prompt test cases
                        prompts = tc.get("prompts")
                        if prompts and isinstance(prompts, list):
                            base_name = tc.get("name", tc.get("rule_name", "") + " test")
                            for i, prompt in enumerate(prompts, 1):
                                expanded = copy.deepcopy(tc)
                                expanded["prompt"] = prompt
                                expanded["name"] = f"{base_name} [{i}/{len(prompts)}]"
                                expanded.pop("prompts", None)
                                test_cases.append(expanded)
                        else:
                            test_cases.append(tc)
    return test_cases


def load_rules_from_file(
    rule_file: str, rules_dir: str
) -> Dict[str, NovaRule]:
    """
    Parse a rule file and return a dict of rule_name -> NovaRule.
    """
    fpath = os.path.join(rules_dir, rule_file)
    parser = NovaRuleFileParser()
    rules = parser.parse_file(fpath)
    return {rule.name: rule for rule in rules}


def run_test(
    rule: NovaRule,
    prompt: str,
    expected_match: bool,
    llm_evaluator: Optional[LLMEvaluator] = None,
    verbose: bool = False,
) -> Tuple[str, str]:
    """
    Run a single test case against a rule.

    This function orchestrates the execution of a single test case. It initializes
    the `NovaMatcher` with the appropriate evaluators (keyword, semantic, and
    optionally LLM) and then runs the matcher against the provided prompt.

    The function returns a status string ("pass", "fail", or "skip") and a
    detailed message explaining the outcome. A test is marked as "skip" if it
    requires LLM evaluation but no LLM evaluator is provided.

    Args:
        rule: The `NovaRule` object to be tested.
        prompt: The input prompt to test against the rule.
        expected_match: A boolean indicating the expected outcome.
        llm_evaluator: An optional `LLMEvaluator` instance. If provided, LLM-based
                       evaluation will be performed.
        verbose: If `True`, includes additional details in the output message.

    Returns:
        A tuple containing the test status ("pass", "fail", or "skip") and a
        detailed message about the test result.
    """
    rule_needs_llm = needs_llm(rule)

    matcher = NovaMatcher(
        rule,
        semantic_evaluator=get_semantic_evaluator(),
        llm_evaluator=llm_evaluator,
        create_llm_evaluator=True if llm_evaluator else False,
    )
    result = matcher.check_prompt(prompt)
    actual_match = result["matched"]

    if actual_match == expected_match:
        detail = f"matched={actual_match}, expected={expected_match}"
        if verbose and result.get("matching_keywords"):
            detail += f", keywords={result['matching_keywords']}"
        return "pass", detail

    # Mismatch: expected True but got False, rule needs LLM, and no LLM evaluator provided
    if (
        expected_match
        and not actual_match
        and rule_needs_llm
        and not llm_evaluator
    ):
        return "skip", "condition requires LLM evaluation (run with --llm-testing)"

    detail = f"matched={actual_match}, expected={expected_match}"
    if verbose and result.get("matching_keywords"):
        detail += f", keywords={result['matching_keywords']}"
    if result.get("llm_evaluation"):
        detail += f", llm_result={result['llm_evaluation']}"
    return "fail", detail


def run(
    rules_dir: str,
    tests_dir: str,
    verbose: bool = False,
    llm_testing: bool = False,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    **kwargs,
) -> Tuple[int, Dict[str, Any]]:
    """
    Execute the main logic for rule testing.

    This function serves as the main entry point for the test runner. It handles
    the discovery and loading of test cases, initialization of the LLM evaluator
    (if requested), and the iteration over all test cases.

    The function aggregates the results of all test cases and prints a summary
    at the end. It returns an exit code (0 for success, 1 for failure) and a
    dictionary containing the counts of passed, failed, and skipped tests.

    Args:
        rules_dir: The directory containing the `.nov` rule files.
        tests_dir: The directory containing the YAML test case files.
        verbose: If `True`, enables detailed per-test logging.
        llm_testing: If `True`, enables LLM-based evaluation.
        llm_provider: The name of the LLM provider to use (e.g., "openai").
        llm_model: The name of the specific LLM model to use.
        **kwargs: Additional keyword arguments.

    Returns:
        A tuple containing the exit code and a dictionary with the test results.
    """
    global _llm_evaluator
    rules_dir = os.path.abspath(rules_dir)
    tests_dir = os.path.abspath(tests_dir)

    if not os.path.isdir(tests_dir):
        print_fail(f"Tests directory not found: {tests_dir}")
        return 1, {"passed": 0, "failed": 1, "skipped": 0}

    # Setup LLM evaluator if requested
    if llm_testing:
        if not llm_provider:
            print_fail("LLM testing enabled, but --llm-provider is not specified.")
            return 1, {"passed": 0, "failed": 1, "skipped": 0}
        try:
            _llm_evaluator = get_validated_evaluator(
                llm_provider, model=llm_model, verbose=verbose
            )
            print_header(f"LLM testing enabled with {llm_provider} (model: {llm_model or 'default'})")
        except ValueError as e:
            print_fail(f"Failed to initialize LLM evaluator: {e}")
            return 1, {"passed": 0, "failed": 1, "skipped": 0}

    test_cases = load_test_cases(tests_dir)
    if not test_cases:
        print_warn("No YAML test case files found")
        return 0, {"passed": 0, "failed": 0, "skipped": 0}

    print_header(f"Rule Testing: {len(test_cases)} test case(s)")

    # Cache parsed rule files
    rule_cache: Dict[str, Dict[str, NovaRule]] = {}

    passed = 0
    failed = 0
    skipped = 0

    for tc in test_cases:
        rule_file = tc.get("_rule_file", "")
        rule_name = tc.get("rule_name", "")
        test_name = tc.get("name", f"{rule_name} test")
        prompt = tc.get("prompt", "")
        expected_match = tc.get("expected_match", False)

        if not prompt:
            print_warn(f"{test_name}: missing 'prompt' field, skipping")
            skipped += 1
            continue

        # Load rule file if not cached
        if rule_file not in rule_cache:
            try:
                rule_cache[rule_file] = load_rules_from_file(rule_file, rules_dir)
            except (NovaParserError, FileNotFoundError) as e:
                print_fail(f"{test_name}: Cannot load rule file '{rule_file}': {e}")
                failed += 1
                continue

        # Find the specific rule
        rules_in_file = rule_cache[rule_file]
        if rule_name not in rules_in_file:
            print_fail(
                f"{test_name}: Rule '{rule_name}' not found in '{rule_file}'. "
                f"Available: {', '.join(rules_in_file.keys())}"
            )
            failed += 1
            continue

        rule = rules_in_file[rule_name]
        status, detail = run_test(
            rule, prompt, expected_match, llm_evaluator=_llm_evaluator, verbose=verbose
        )

        if status == "skip":
            skipped += 1
            if verbose:
                print_warn(f"{test_name} ({rule_name}): {detail}")
        elif status == "pass":
            passed += 1
            if verbose:
                print_pass(f"{test_name} ({rule_name}): {detail}")
        else:
            failed += 1
            print_fail(f"{test_name} ({rule_name}): {detail}")

    print_summary(passed, failed, skipped, third_label="skipped")
    exit_code = 0 if failed == 0 else 1
    return exit_code, {"passed": passed, "failed": failed, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(
        description="Run YAML-driven keyword and LLM tests against Nova rules."
    )
    parser.add_argument(
        "--rules-dir", default=".",
        help="Path to directory containing .nov rule files (default: current dir)"
    )
    parser.add_argument(
        "--tests-dir", default="tests",
        help="Path to directory containing YAML test case files (default: tests/)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show per-test details including skipped tests"
    )
    parser.add_argument(
        "--llm-testing", action="store_true",
        help="Enable LLM-based evaluation for tests that require it"
    )
    parser.add_argument(
        "--llm-provider", type=str, default=None,
        choices=["openai", "anthropic", "azure", "ollama", "groq"],
        help="Specify the LLM provider to use (e.g., 'openai', 'ollama')"
    )
    parser.add_argument(
        "--llm-model", type=str, default=None,
        help="Specify the model name for the LLM provider"
    )
    args = parser.parse_args()

    colorama_init()
    exit_code, _ = run(
        args.rules_dir,
        tests_dir=args.tests_dir,
        verbose=args.verbose,
        llm_testing=args.llm_testing,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
