"""Runner: orchestrates benchmark runs for a schema against a test group."""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .session_parser import parse_session, parse_session_from_offset, SessionMetrics
from .validator import load_assertions, validate_step, ValidationResult


@dataclass
class StepResult:
    step_name: str
    passed: bool
    attempts: int
    metrics: SessionMetrics | None = None
    context_tokens: int = 0  # cumulative context after this step
    failures: list[str] = field(default_factory=list)


@dataclass
class GroupResult:
    group_name: str
    schema_name: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.steps)

    @property
    def total_attempts(self) -> int:
        return sum(s.attempts for s in self.steps)

    @property
    def cost_score(self) -> int:
        return sum(
            s.metrics.cost_score for s in self.steps if s.metrics is not None
        )

    @property
    def total_turns(self) -> int:
        return sum(
            s.metrics.turn_count for s in self.steps if s.metrics is not None
        )

    @property
    def context_tokens(self) -> int:
        """Cumulative context after last passing step."""
        for s in reversed(self.steps):
            if s.context_tokens > 0:
                return s.context_tokens
        return 0


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
    group_dir: Path,
    step_dir: Path,
    extension_path: Path,
    session_path: Path,
    max_retries: int = 3,
) -> StepResult:
    """Run a single edit step with retries.

    Uses a shared session file across retries so the agent sees
    previous attempts and feedback as conversation context.

    Metrics are parsed from only the NEW entries added by this step
    (using byte offsets), avoiding double-counting across steps.
    """
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

    # Load assertions — catch YAML errors
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
        # Record session file offset before this pi invocation
        offset_before = (
            session_path.stat().st_size if session_path.exists() else 0
        )

        process = run_pi(
            prompt=prompt,
            extension_path=extension_path,
            session_path=session_path,
            cwd=workspace,
        )

        if process is None:
            # Timeout
            if attempt < max_retries:
                prompt = (
                    "The previous attempt timed out. Please try again "
                    "with a simpler approach."
                )
                continue
            return StepResult(
                step_name=step_name,
                passed=False,
                attempts=max_retries,
                failures=["Timeout — all retries exhausted"],
            )

        # Validate
        try:
            validation = validate_step(workspace, assertions)
        except Exception as e:
            validation = ValidationResult(
                passed=False,
                failures=[f"Validation error: {e}"],
            )

        if validation.passed:
            # Parse step-only metrics (new entries since offset_before)
            step_metrics = None
            if session_path.exists():
                try:
                    step_metrics = parse_session_from_offset(
                        session_path, offset_before
                    )
                except Exception:
                    pass

            # Parse cumulative context (full session, once-counted)
            context_after = 0
            if session_path.exists():
                try:
                    full = parse_session(session_path)
                    context_after = full.context_tokens
                except Exception:
                    pass

            return StepResult(
                step_name=step_name,
                passed=True,
                attempts=attempt,
                metrics=step_metrics,
                context_tokens=context_after,
            )

        # On failure, construct a retry prompt with the errors
        if attempt < max_retries:
            error_text = "\n".join(validation.failures)
            prompt = (
                f"The edit didn't pass validation. Issues found:\n"
                f"{error_text}\n\n"
                f"Please fix these issues."
            )

    # All retries exhausted
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
    """Run a full test group (all steps) with one schema extension."""
    group_name = group_dir.name
    schema_name = extension_path.parent.name

    initial_dir = group_dir / "initial"
    if not initial_dir.exists():
        return GroupResult(
            group_name=group_name,
            schema_name=schema_name,
        )

    # Prepare workspace
    workspace = workspace_base / f"{group_name}-{schema_name}"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(initial_dir, workspace)

    result = GroupResult(group_name=group_name, schema_name=schema_name)
    session_path = workspace / ".bench-session.jsonl"

    # Run steps in order
    step_dirs = sorted(
        [d for d in group_dir.iterdir() if d.is_dir() and d.name.startswith("step-")],
        key=lambda d: d.name,
    )

    for step_dir in step_dirs:
        step_result = run_step(
            workspace=workspace,
            group_dir=group_dir,
            step_dir=step_dir,
            extension_path=extension_path,
            session_path=session_path,
            max_retries=max_retries,
        )
        result.steps.append(step_result)
        if not step_result.passed:
            break

    return result
