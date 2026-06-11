"""Runner: orchestrates benchmark runs for a schema against a test group."""

import shutil
import subprocess
import time
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
class RunResult:
    """Result of a single run (all steps) of a group."""
    passed: bool
    steps: list[StepResult] = field(default_factory=list)
    metrics: SessionMetrics | None = None


@dataclass
class GroupResult:
    group_name: str
    schema_name: str
    runs_completed: int = 0
    runs_total: int = 0
    runs: list[RunResult] = field(default_factory=list)
    metrics_avg: SessionMetrics | None = None

    @property
    def passed(self) -> bool:
        return self.runs_completed > 0 and all(r.passed for r in self.runs)

    @property
    def cost_score(self) -> int:
        if not self.runs:
            return 0
        return sum(r.metrics.cost_score for r in self.runs if r.metrics) // len(self.runs)

    @property
    def total_turns(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.metrics.turn_count for r in self.runs if r.metrics) / len(self.runs)

    @property
    def context_tokens(self) -> int:
        if not self.runs:
            return 0
        return sum(r.metrics.context_tokens for r in self.runs if r.metrics) // len(self.runs)


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
    deadline: float,
) -> StepResult | None:
    """Run a single edit step, retrying until pass or deadline expires.

    Returns None if the step could not complete (timeout during pi call
    or deadline expired). Returns StepResult otherwise.
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

    try:
        assertions = load_assertions(validate_path)
    except Exception as e:
        return StepResult(
            step_name=step_name,
            passed=False,
            attempts=0,
            failures=[f"YAML parse error in {validate_path}: {e}"],
        )

    attempt = 0
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return None  # deadline expired, abort this run

        attempt += 1
        process = run_pi(
            prompt=prompt,
            extension_path=extension_path,
            session_path=session_path,
            cwd=workspace,
            timeout=max(1, int(remaining)),
        )

        if process is None:
            # pi call timed out (used all remaining time)
            return None

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

        # Retry with feedback
        error_text = "\n".join(validation.failures)
        prompt = (
            f"The edit didn't pass validation. Issues found:\n"
            f"{error_text}\n\n"
            f"Please fix these issues."
        )


def run_single(
    workspace: Path,
    group_dir: Path,
    extension_path: Path,
    session_path: Path,
    deadline: float,
) -> RunResult | None:
    """Run all steps of a group once. Returns None if timed out."""
    run_result = RunResult(passed=True, steps=[])

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
            deadline=deadline,
        )

        if step_result is None:
            return None  # timeout during step → abandon this run

        run_result.steps.append(step_result)
        if not step_result.passed:
            run_result.passed = False
            break

    # Parse metrics from the completed session
    if session_path.exists():
        try:
            run_result.metrics = parse_session(session_path)
        except Exception:
            pass

    return run_result


def run_group(
    workspace_base: Path,
    group_dir: Path,
    extension_path: Path,
    runs: int = 1,
    timeout: int = 600,
) -> GroupResult:
    """Run a test group N times with one schema extension.

    Each run gets its own workspace and session file. Metrics are
    averaged across completed runs. Timed-out runs are excluded.
    """
    group_name = group_dir.name
    schema_name = extension_path.parent.name

    initial_dir = group_dir / "initial"
    if not initial_dir.exists():
        return GroupResult(group_name=group_name, schema_name=schema_name)

    result = GroupResult(
        group_name=group_name,
        schema_name=schema_name,
        runs_total=runs,
    )

    for run_idx in range(1, runs + 1):
        workspace = workspace_base / f"{group_name}-{schema_name}" / f"run-{run_idx}"
        if workspace.exists():
            shutil.rmtree(workspace)
        shutil.copytree(initial_dir, workspace)

        session_path = workspace / ".bench-session.jsonl"
        deadline = time.time() + timeout

        run_result = run_single(
            workspace=workspace,
            group_dir=group_dir,
            extension_path=extension_path,
            session_path=session_path,
            deadline=deadline,
        )

        if run_result is not None:
            result.runs.append(run_result)
            result.runs_completed += 1

    return result
