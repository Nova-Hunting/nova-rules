# Contributing to Nova Rules

Thank you for your interest in contributing to the Nova rules collection! This guide will walk you through the process of creating and validating a new Nova rule.

## Rule Structure

Nova rules use a custom `.nov` format. Each rule follows this basic structure:

```nova
rule YourRuleName
{
    meta:
        description = "A clear description of what this rule detects"
        author = "Your Name or @handle"
        version = "1.0.0"
        category = "category/subcategory"
        severity = "medium"
        uuid = "generate-a-fresh-v4-uuid"
        date = "YYYY-MM-DD"
        // Optional fields
        reference = "URL or report name"
        modified = "YYYY-MM-DD"

    keywords:
        $keyword1 = "exact string"
        $keyword2 = /regex_pattern/i

    semantics:
        $concept1 = "semantic description of intent" (0.35)

    llm:
        $check1 = "Natural language instruction for the LLM to verify" (0.5)

    condition:
        any of keywords.* or semantics.$concept1 or llm.$check1
}
```

## Metadata Requirements

All rules must include the following fields in the `meta` section:

| Field | Requirement | Description |
| :--- | :--- | :--- |
| `description` | Required | High-level explanation of the detection goal. |
| `author` | Required | Credit for the rule creator. |
| `version` | Required | Semantic versioning (e.g., `1.0.0`). |
| `category` | Required | Must match a value in [CATEGORIES.md](CATEGORIES.md) (following the [official taxonomy](https://promptintel.novahunting.ai/taxonomy)) in the format: `category/subcategory`. |
| `severity` | Required | One of: `low`, `medium`, `high`, `critical`. |
| `uuid` | Required | A unique Version 4 UUID. |
| `date` | Required | Initial creation date in `YYYY-MM-DD` format. |
| `hash` | Optional | File hash for integrity verification. |
| `reference` | Optional | External link to research, reports, or examples. |
| `modified` | Optional | Last update date in `YYYY-MM-DD` format. |

> **Note**: Metadata fields are strictly validated. Including unknown or unofficial fields will cause a validation error.

## Detection Sections

1. **`keywords`**: Direct string matching or regular expressions. Best for specific payloads or known malicious strings.
2. **`semantics`**: Intent-based detection using semantic similarity. Requires a threshold (0.0 to 1.0).
3. **`llm`**: Powerful natural language verification. Use this for complex logic that keywords can't capture. Requires a threshold.
4. **`condition`**: The boolean logic that determines if the rule triggers.

## Rule Requirements

- **Naming Convention**: All rules must follow the `PascalCase` format (e.g., `SuspiciousBase64Injection` instead of `suspicious_base64`).
- **Unique Rule Names**: Every rule must have a unique name across the entire repository.
- **File Extensions**: All rule files must use the `.nov` extension. Other extensions like `.yara` or `.rule` are not permitted.
- **Granular Categories**: Always use the most specific subcategory available in [CATEGORIES.md](CATEGORIES.md) (based on the [official taxonomy](https://promptintel.novahunting.ai/taxonomy)).
- **Test Your Rules**: Ensure your conditions are not too broad (preventing false positives) or too narrow (preventing false negatives). Every new rule should be accompanied by a test case in a corresponding YAML file in the `tests/` directory.
- **UUIDs**: Never reuse a UUID from another rule. Use a Version 4 UUID generator.


## Validation

Before submitting a rule, you must ensure it passes the metadata and syntax validation.

### Run Metadata Validation
```bash
python3 validation/validate_metadata.py --rules-dir . -v
```

### Run Syntax Validation
```bash
python3 validation/validate_syntax.py --rules-dir . -v
```

## Rule Testing

Testing is a critical part of the rule development process. Nova rules are tested using YAML files located in the `tests/` directory.

### Test Format

Each rule should have a corresponding test file (e.g., `your_rule_tests.yaml`). The test runner enforces a strict schema for these files to ensure consistency and reliability.

**Mandatory Fields:**
- `rule_file`: **(Top-level)** The relative path to the `.nov` file containing the rule(s).
- `name`: **(Per test)** A descriptive name for the test case.
- `rule_name`: **(Per test)** The exact name of the rule to be tested (as defined in the `.nov` file). Note: This must be specified for every test case.
- `expected_match`: **(Per test)** A boolean (`true` or `false`) indicating if the rule is expected to trigger.
- `prompt` OR `prompts`: **(Per test)** The input string(s) to test.
    - Use `prompt` for a single test string.
    - Use `prompts` for a list of strings (each will be treated as a separate test case).
    - **Note:** You cannot define both `prompt` and `prompts` in the same test case.

```yaml
rule_file: "your_rule.nov"
tests:
  - name: "Test case description (positive)"
    rule_name: "YourRuleName"
    prompts:
      - "A prompt that SHOULD trigger the rule"
      - "Another prompt that SHOULD trigger the rule"
    expected_match: true

  - name: "Test case description (negative)"
    rule_name: "YourRuleName"
    prompt: "A benign prompt that should NOT trigger the rule"
    expected_match: false
```

### Running Tests

To run tests with detailed output:
```bash
python3 tests/test_rules.py --rules-dir . --tests-dir tests/ -v
```
This script works in CI without loading the llm-testing flag (default to False) to avoid having delays/API config but it works also offilne by running `python3 tests/test_rules.py --llm-testing --llm-provider <provider>`
The two scenarios are explained below:

### Scenario 1: CI Mode (Default)
This is when you run `python3 tests/test_rules.py` without the `--llm-testing` flag. The LLM evaluator is **not** loaded.

| If the Rule's condition is... | And the prompt... | And the test `expected_match` is... | The Result will be... | Because... |
| :--- | :--- | :--- | :--- | :--- |
| Keyword-only | **Matches** the keyword logic | `true` | **PASS** | The rule correctly matched on its keyword logic. |
| Semantic-only | **Matches** the semantic logic | `true` | **PASS** | The rule correctly matched on its semantic logic. |
| Keyword-only or Semantic-only | **Does not** match the logic | `false` | **PASS** | The rule correctly ignored a prompt it wasn't supposed to match. |
| Keyword **OR** LLM | **Matches** the keyword logic | `true` | **PASS** | The rule matched on its keyword part. The LLM condition is not needed and is ignored. |
| Semantic **OR** LLM | **Matches** the semantic logic | `true` | **PASS** | The rule matched on its semantic part. The LLM condition is not needed and is ignored. |
| LLM-only **or** (Keyword **OR** LLM) **or** (Semantic **OR** LLM) | **Only** matches the LLM logic | `true` | **SKIP** | The test expects a match, but the only way to achieve it is via the LLM, which is disabled. The test is skipped to avoid a CI failure. |
| LLM-only **or** (Keyword **OR** LLM) **or** (Semantic **OR** LLM) | **Does not** match any logic | `false` | **PASS** | The test correctly expected no match, and since the LLM is off, no match occurred. |
| Any rule type | **Does not** match the keyword/semantic logic | `true` | **FAIL** | The test expected a match based on the non-LLM logic, but it failed to do so. |

---

### Scenario 2: Full Evaluation Mode
This is when you run with `python3 tests/test_rules.py --llm-testing --llm-provider <provider>`. The LLM evaluator is **loaded and active**.

| If the Rule's condition is... | And the prompt... | And the test `expected_match` is... | The Result will be... | Because... |
| :--- | :--- | :--- | :--- | :--- |
| LLM-only | **Only** matches the LLM logic | `true` | **PASS** / **FAIL** | A **real API call** is made to the LLM. The test passes only if the LLM correctly identifies the prompt as harmful. This validates the LLM prompt itself. |
| (Keyword **OR** LLM) **or** (Semantic **OR** LLM) | **Only** matches the LLM logic | `true` | **PASS** / **FAIL** | A **real API call** is made to the LLM. The test passes only if the LLM correctly identifies the prompt as harmful. This validates the LLM prompt itself. |
| LLM-only **or** (Keyword **OR** LLM) **or** (Semantic **OR** LLM) | **Does not** match any logic | `false` | **PASS** / **FAIL** | A **real API call** is made. The test passes only if the LLM correctly determines the prompt is benign. |
| Keyword-only | **Matches** the keyword logic | `true` | **PASS** | Same as in CI mode. The rule correctly matched, and the LLM is not relevant for this rule. |
| Semantic-only | **Matches** the semantic logic | `true` | **PASS** | Same as in CI mode. The rule correctly matched, and the LLM is not relevant for this rule. |
| Keyword **OR** LLM | **Matches** the keyword logic | `true` | **PASS** | The rule's condition is satisfied by the keyword match. Due to short-circuit evaluation, the LLM is likely not even called, saving time and resources. |
| Semantic **OR** LLM | **Matches** the semantic logic | `true` | **PASS** | The rule's condition is satisfied by the semantic match. Due to short-circuit evaluation, the LLM is likely not even called, saving time and resources. |


## CI Validation

The GitHub Actions workflow runs four stages on push/PR to `main`:

1. **Syntax Validation** — parses all `.nov` files.
2. **Metadata Validation** — checks required meta fields (runs after syntax).
3. **Lint** — checks for best practices and naming conventions (runs after syntax).
4. **Rule Tests** — validates and runs YAML test cases (runs after syntax).
    - **YAML Linting**: Test files are strictly linted using `yamllint`. Incorrect indentation or formatting will cause the job to fail.
    - **Functional Tests**: Checks keyword and semantic matching logic.

