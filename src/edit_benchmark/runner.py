"""Runner: orchestrates benchmark runs for a schema against a test group."""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .session_parser import parse_session, SessionMetrics
from .validator import load_assertions, validate_step, ValidationResult


@dataclass
class StepResult:
    step_name: str
    passed: bool
    attempts: int
    failures: list[str] = field(default_factory=list)


@dataclass
class GroupResult:
    group_name: str
    schema_name: str
    steps: list[StepResult] = field(default_factory=list)
    metrics: SessionMetrics | None = None

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.steps)

    @property
    def total_attempts(self) -> int:
        return sum(s.attempts for s in self.steps)

    @property
    def cost_score(self) -> int:
        return self.metrics.cost_score if self.metrics else 0

    @property
    def total_turns(self) -> int:
        return self.metrics.turn_count if self.metrics else 0

    @property
    def context_tokens(self) -> int:
        return self.metrics.context_tokens if self.metrics else 0


def run_pi(
    prompt: str,
    extension_path: Path,
    session_path: Path,
    cwd: Path,
    timeout: int = 120,
):
    """Run pi in print mode. Returns CompletedProcess or None on timeout."""
    pi_exe = shutil.which("pi.cmd") or shutil.which("pi") or "pi"
    cmd = [
        pi_exe,
        "-p", prompt,
        "-e", str(extension_path),
        "--session", str(session_path),
    ]
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None


def run_step(
    workspace: Path,
    step_dir: Path,
    extension_path: Path,
    session_path: Path,
    max_retries: int = 3,
) -> StepResult:
    """Run a single edit step with retries using a shared session file."""
    step_name = step_dir.name

    instruction_path = step_dir / "instruction.md"
    validate_path = step_dir / "validate.yaml"

    if not instruction_path.exists():
        return StepResult(
            step_name=step_name,
            passed=False,
            attempts=0,
            failures=[f"Missing instruction.md in {step_dir}"],
        )

    prompt = instruction_path.read_text(encoding="utf-8").strip()

    try:
        assertions = load_assertions(validate_path)
    except Exception as e:
        return StepResult(
            step_name=step_name,
            passed=False,
            attempts=0,
            failures=[f"YAML parse error in {validate_path}: {e}"],
        )

    for attempt in range(1, max_retries + 1):
        process = run_pi(
            prompt=prompt,
            extension_path=extension_path,
            session_path=session_path,
            cwd=workspace,
        )

        if process is None:
            if attempt < max_retries:
                prompt = "The previous attempt timed out. Please try again with a simpler approach."
                continue
            return StepResult(
                step_name=step_name,
                passed=False,
                attempts=max_retries,
                failures=["Timeout — all retries exhausted"],
            )

        try:
            validation = validate_step(workspace, assertions)
        except Exception as e:
            validation = ValidationResult(
                passed=False,
                failures=[f"Validation error: {e}"],
            )

        if validation.passed:
            return StepResult(
                step_name=step_name,
                passed=True,
                attempts=attempt,
            )

        if attempt < max_retries:
            error_text = "\n".join(validation.failures)
            prompt = (
                f"The edit didn't pass validation. Issues found:\n"
                f"{error_text}\n\n"
                f"Please fix these issues."
            )

    return StepResult(
        step_name=step_name,
        passed=False,
        attempts=max_retries,
        failures=validation.failures,
    )


def run_group(
    workspace_base: Path,
    group_dir: Path,
    extension_path: Path,
    max_retries: int = 3,
) -> GroupResult:
    """Run a full test group (all steps) with one schema extension.

    All steps share the same workspace and session file. Metrics are
    parsed once from the final session.
    """
    group_name = group_dir.name
    schema_name = extension_path.parent.name

    initial_dir = group_dir / "initial"
    if not initial_dir.exists():
        return GroupResult(group_name=group_name, schema_name=schema_name)

    workspace = workspace_base / f"{group_name}-{schema_name}"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(initial_dir, workspace)

    result = GroupResult(group_name=group_name, schema_name=schema_name)
    session_path = workspace / ".bench-session.jsonl"

    step_dirs = sorted(
        [d for d in group_dir.iterdir() if d.is_dir() and d.name.startswith("step-")],
        key=lambda d: d.name,
    )

    for step_dir in step_dirs:
        step_result = run_step(
            workspace=workspace,
            step_dir=step_dir,
            extension_path=extension_path,
            session_path=session_path,
            max_retries=max_retries,
        )
        result.steps.append(step_result)
        if not step_result.passed:
            break

    # Parse metrics once from the final session
    if session_path.exists():
        try:
            result.metrics = parse_session(session_path)
        except Exception:
            pass

    return result
