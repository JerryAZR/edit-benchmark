"""Parse pi session JSONL files to extract metrics."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    tool_name: str
    is_error: bool
    call_index: int


@dataclass
class TurnMetrics:
    turn_index: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class SessionMetrics:
    turns: list[TurnMetrics] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        return sum(t.input_tokens for t in self.turns)

    @property
    def total_output_tokens(self) -> int:
        return sum(t.output_tokens for t in self.turns)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def tool_errors(self) -> int:
        return sum(
            1 for t in self.turns for tc in t.tool_calls if tc.is_error
        )

    @property
    def cost_score(self) -> int:
        """Weighted cost: cache=1x, input=10x, output=40x. Lower is cheaper."""
        total = 0
        for t in self.turns:
            total += t.cache_read_tokens * 1
            total += t.input_tokens * 10
            total += t.output_tokens * 40
        return total

    @property
    def context_tokens(self) -> int:
        """Context size at end of session, counted once (no prefix double-count).

        The last turn's cacheRead includes all previously cached content;
        input+output are the new uncached tokens. Sum gives the total unique
        tokens that appeared in the conversation.
        """
        if not self.turns:
            return 0
        last = self.turns[-1]
        return last.cache_read_tokens + last.input_tokens + last.output_tokens

    @property
    def tool_calls_by_name(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.turns:
            for tc in t.tool_calls:
                counts[tc.tool_name] = counts.get(tc.tool_name, 0) + 1
        return counts

    @property
    def is_empty(self) -> bool:
        return self.turn_count == 0 and self.total_tokens == 0

    def summary(self) -> dict[str, Any]:
        return {
            "turns": self.turn_count,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "context_tokens": self.context_tokens,
            "cost_score": self.cost_score,
            "tool_errors": self.tool_errors,
            "tool_calls": self.tool_calls_by_name,
        }


def _parse_lines(lines: Iterator[str]) -> SessionMetrics:
    """Core parsing loop shared by parse_session and parse_session_from_offset."""
    metrics = SessionMetrics()
    turn_index = 0
    call_index_in_turn = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if entry.get("type") != "message":
            continue

        msg = entry.get("message", {})
        role = msg.get("role", "")

        if role == "assistant":
            turn = TurnMetrics(
                turn_index=turn_index,
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
            )

            usage = msg.get("usage", {})
            if usage:
                turn.input_tokens = usage.get("input", 0)
                turn.output_tokens = usage.get("output", 0)
                turn.cache_read_tokens = usage.get("cacheRead", 0)
                turn.cache_write_tokens = usage.get("cacheWrite", 0)

            metrics.turns.append(turn)
            turn_index += 1
            call_index_in_turn = 0

        elif role == "toolResult":
            if metrics.turns:
                current_turn = metrics.turns[-1]
                tool_name = msg.get("toolName", msg.get("name", "unknown"))
                is_error = msg.get("isError", False)

                current_turn.tool_calls.append(
                    ToolCall(
                        tool_name=tool_name,
                        is_error=is_error,
                        call_index=call_index_in_turn,
                    )
                )
                call_index_in_turn += 1

    return metrics


def parse_session(session_path: Path) -> SessionMetrics:
    """Parse an entire pi session JSONL file and extract metrics."""
    with open(session_path, "r", encoding="utf-8") as f:
        metrics = _parse_lines(f)

    if metrics.is_empty and session_path.stat().st_size > 0:
        logger.warning(
            "Session file %s has %d bytes but produced no metrics. "
            "Format may have changed.",
            session_path, session_path.stat().st_size,
        )

    return metrics


def parse_session_from_offset(
    session_path: Path, start_offset: int
) -> SessionMetrics:
    """Parse session JSONL entries added after start_offset bytes.

    Useful for multi-step sessions where the file is cumulative but you
    only want metrics for the current step.
    """
    with open(session_path, "r", encoding="utf-8") as f:
        f.seek(start_offset)
        return _parse_lines(f)
