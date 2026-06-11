"""Assertion-based validation for edit results."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore


@dataclass
class ValidationResult:
    passed: bool
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.passed


def load_assertions(validate_path: Path) -> dict:
    """Load validate.yaml and return assertions dict."""
    if not validate_path.exists():
        return {}
    with open(validate_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_file(file_path: Path, assertions: dict) -> ValidationResult:
    """Run assertions against a single file.

    Supported assertion keys:
        must_contain: list[str]    - Every pattern must be found in file
        must_not_contain: list[str] - No pattern may be found in file
    """
    failures: list[str] = []

    if not file_path.exists():
        return ValidationResult(
            passed=False,
            failures=[f"File not found: {file_path}"],
        )

    content = file_path.read_text(encoding="utf-8")

    for pattern in assertions.get("must_contain", []):
        if not re.search(pattern, content):
            failures.append(
                f"{file_path}: must_contain pattern not found: {pattern!r}"
            )

    for pattern in assertions.get("must_not_contain", []):
        if re.search(pattern, content):
            failures.append(
                f"{file_path}: must_not_contain pattern matched: {pattern!r}"
            )

    return ValidationResult(
        passed=len(failures) == 0,
        failures=failures,
    )


def validate_step(workspace: Path, assertions: dict) -> ValidationResult:
    """Run assertions for a step, supporting multi-file validation.

    Top-level assertions with 'file' key:
        file: src/api.py
        must_contain: [...]

    Also supports per-file dicts:
        files:
          src/api.py:
            must_contain: [...]
          src/utils.py:
            must_not_contain: [...]
    """
    failures: list[str] = []

    # Single file mode: top-level 'file' key
    if "file" in assertions:
        file_path = workspace / assertions["file"]
        result = validate_file(file_path, assertions)
        failures.extend(result.failures)

    # Multi-file mode: 'files' dict
    if "files" in assertions:
        for rel_path, file_assertions in assertions["files"].items():
            file_path = workspace / rel_path
            result = validate_file(file_path, file_assertions)
            failures.extend(result.failures)

    return ValidationResult(
        passed=len(failures) == 0,
        failures=failures,
    )
