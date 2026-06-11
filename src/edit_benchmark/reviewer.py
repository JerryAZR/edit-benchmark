"""Reviewer: classify agent tool usage from a formatted session log.

Spawns pi in print mode with a strict classification prompt, parses the
JSON output, and returns structured results.
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

REVIEWER_PROMPT = """Analyze the following AI agent session log. The agent performed multi-step edits on a codebase using a single edit tool.

For each edit tool invocation in the session, classify it into exactly ONE of:

- tool_rejected: the tool returned an error and the agent had to retry or adjust
  (any error: stale anchor, no match, patch failed, file not found, permission denied, etc.)

- tool_succeeded_warning: the edit was applied but the tool gave a warning,
  truncated output, or said something like "Anchors omitted", "use read for edits",
  or any indication the result is incomplete or unreliable

- tool_succeeded_wrong: the edit was applied without error or warning, but the
  result is clearly wrong — the agent edited the wrong function, the wrong file,
  missed a call site, introduced a syntax error, or the output doesn't match what
  the agent intended

- tool_succeeded_correct: clean edit, no errors, no warnings, correct target

Also classify each turn's overall strategy:

- correct: the agent's approach was sensible and direct
- inefficient: the agent took unnecessary extra steps (redundant reads, searching
  when the target is obvious, unrelated tool calls)
- confused: the agent targeted the wrong file/function, misunderstood the task,
  or made errors that show fundamental confusion

For warnings unrelated to individual edits (e.g. agent spent many turns searching
for a file), add them to turn-level warnings.

Respond with ONLY this JSON structure, no other text:

{
  "turns": [
    {
      "index": 1,
      "strategy": "correct",
      "turn_warnings": [],
      "edits": [
        {
          "tool": "edit",
          "classification": "tool_succeeded_correct",
          "edit_warnings": []
        }
      ]
    }
  ],
  "overall": {
    "biggest_friction": "none"
  }
}

Here is the session log:

"""


@dataclass
class EditClassification:
    tool: str
    classification: str  # tool_rejected | tool_succeeded_warning | tool_succeeded_wrong | tool_succeeded_correct
    warnings: list[str] = field(default_factory=list)


@dataclass
class TurnClassification:
    index: int
    strategy: str  # correct | inefficient | confused
    warnings: list[str] = field(default_factory=list)
    edits: list[EditClassification] = field(default_factory=list)


@dataclass
class ReviewResult:
    turns: list[TurnClassification] = field(default_factory=list)
    biggest_friction: str = "none"
    raw_response: str = ""

    @property
    def total_edits(self) -> int:
        return sum(len(t.edits) for t in self.turns)

    @property
    def correct_edits(self) -> int:
        return sum(
            1 for t in self.turns for e in t.edits
            if e.classification == "tool_succeeded_correct"
        )

    @property
    def rejected_edits(self) -> int:
        return sum(
            1 for t in self.turns for e in t.edits
            if e.classification == "tool_rejected"
        )

    @property
    def warned_edits(self) -> int:
        return sum(
            1 for t in self.turns for e in t.edits
            if e.classification == "tool_succeeded_warning"
        )

    @property
    def wrong_edits(self) -> int:
        return sum(
            1 for t in self.turns for e in t.edits
            if e.classification == "tool_succeeded_wrong"
        )

    @property
    def correct_rate(self) -> float:
        if self.total_edits == 0:
            return 1.0
        return self.correct_edits / self.total_edits

    @property
    def rejection_rate(self) -> float:
        if self.total_edits == 0:
            return 0.0
        return self.rejected_edits / self.total_edits

    def summary(self) -> dict:
        return {
            "total_edits": self.total_edits,
            "correct": self.correct_edits,
            "rejected": self.rejected_edits,
            "warned": self.warned_edits,
            "wrong": self.wrong_edits,
            "correct_rate": round(self.correct_rate, 3),
            "rejection_rate": round(self.rejection_rate, 3),
            "biggest_friction": self.biggest_friction,
            "turn_strategies": [t.strategy for t in self.turns],
        }


def _parse_response(text: str) -> dict | None:
    """Extract JSON from pi's response. Tries code blocks first, then raw JSON."""
    # Try ```json ... ``` code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try raw JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: find JSON-like structure
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def review_session(
    session_markdown: str,
    model: str = "deepseek-v4-flash",
    timeout: int = 120,
) -> ReviewResult:
    """Run pi to classify a formatted session log.

    Args:
        session_markdown: Formatted session in markdown (from session_formatter).
        model: Model to use for the reviewer.
        timeout: Timeout for the reviewer invocation.

    Returns:
        ReviewResult with structured classifications.
    """
    import shutil
    import tempfile

    prompt = REVIEWER_PROMPT + "\n" + session_markdown

    # Find pi entry point
    pi_cmd = shutil.which("pi.cmd")
    if not pi_cmd:
        pi_cmd = shutil.which("pi")
    if not pi_cmd:
        raise RuntimeError("pi not found in PATH")

    pi_dir = Path(pi_cmd).parent
    cli_js = pi_dir / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"

    if cli_js.exists():
        cmd = ["node", str(cli_js)]
    else:
        cmd = [pi_cmd]

    cmd += ["-p", prompt, "--model", model]

    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ReviewResult(
            biggest_friction="reviewer_timeout",
            raw_response="Reviewer timed out",
        )

    response = result.stdout.strip()
    parsed = _parse_response(response)

    if parsed is None:
        logger.warning("Failed to parse reviewer JSON response: %s", response[:200])
        return ReviewResult(
            biggest_friction="parse_error",
            raw_response=response,
        )

    turns = []
    for t in parsed.get("turns", []):
        edits = []
        for e in t.get("edits", []):
            edits.append(EditClassification(
                tool=e.get("tool", "unknown"),
                classification=e.get("classification", "tool_succeeded_correct"),
                warnings=e.get("edit_warnings", []),
            ))
        turns.append(TurnClassification(
            index=t.get("index", 0),
            strategy=t.get("strategy", "correct"),
            warnings=t.get("turn_warnings", []),
            edits=edits,
        ))

    overall = parsed.get("overall", {})

    return ReviewResult(
        turns=turns,
        biggest_friction=overall.get("biggest_friction", "none"),
        raw_response=response,
    )
