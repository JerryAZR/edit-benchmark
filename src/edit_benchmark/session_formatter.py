"""Format pi session JSONL into readable markdown for AI review."""

import json
from pathlib import Path
from typing import Any


def _clean_text(text: str) -> str:
    """Strip hashline anchors and clean up tool output for readability."""
    # Remove LINE#HASH: prefix from anchored lines
    import re
    text = re.sub(r'^\d+#[A-Za-z0-9]+:', '', text, flags=re.MULTILINE)
    # Remove --- Anchors X-Y --- separator blocks
    text = re.sub(r'--- Anchors \d+-\d+ ---\n?', '', text)
    return text.strip()


def format_session(session_path: Path) -> str:
    """Convert a pi session JSONL file to readable markdown.

    Returns a markdown string suitable for feeding to a reviewer agent.
    """
    with open(session_path, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    # Extract session metadata
    session_name = "Unnamed session"
    model_id = "unknown"
    cwd = ""
    for entry in lines:
        if entry.get("type") == "session_info":
            session_name = entry.get("name", session_name)
        elif entry.get("type") == "model_change":
            prov = entry.get("provider", "")
            mod = entry.get("modelId", "")
            model_id = f"{prov}/{mod}" if prov else mod
        elif entry.get("type") == "session":
            cwd = entry.get("cwd", "")

    output: list[str] = []
    output.append(f"## Session: {session_name}")
    output.append(f"**Model**: {model_id}")
    if cwd:
        output.append(f"**CWD**: {cwd}")
    output.append("")

    # Group entries into turns
    # A turn starts at each user message and runs until the next user message
    turns: list[list[dict]] = []
    current_turn: list[dict] = []
    for entry in lines:
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        role = msg.get("role", "")
        if role == "user" and current_turn:
            turns.append(current_turn)
            current_turn = []
        current_turn.append(entry)
    if current_turn:
        turns.append(current_turn)

    # Aggregate totals
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_tool_calls = 0
    total_tool_errors = 0

    for ti, turn_entries in enumerate(turns, 1):
        output.append(f"### Turn {ti}")
        output.append("")

        for entry in turn_entries:
            msg = entry.get("message", {})
            role = msg.get("role", "")
            content = msg.get("content", [])
            usage = msg.get("usage", {})

            if role == "user":
                for item in content:
                    text = item.get("text", "")
                    if text.strip():
                        output.append("**User**:")
                        output.append(f"> {text}")
                        output.append("")

            elif role == "assistant":
                if usage:
                    total_input += usage.get("input", 0)
                    total_output += usage.get("output", 0)
                    total_cache_read += usage.get("cacheRead", 0)

                thinking_parts = []
                text_parts = []
                tool_calls_in_msg = []

                for item in content:
                    ct = item.get("type", "")
                    if ct == "thinking":
                        sig = item.get("thinkingSignature", "")
                        # Skip prompt-caching signature blobs
                        if sig == "reasoning_content":
                            thinking_parts.append(item.get("thinking", ""))
                    elif ct == "text":
                        text_parts.append(item.get("text", ""))
                    elif ct == "toolCall":
                        tool_calls_in_msg.append(item)

                if thinking_parts:
                    thinking = " ".join(thinking_parts).strip()
                    if thinking:
                        output.append("**Assistant** (thinking):")
                        for line in thinking.split("\n"):
                            output.append(f"> {line}")
                        output.append("")

                if text_parts:
                    text = "\n\n".join(t.strip() for t in text_parts if t.strip())
                    if text:
                        output.append("**Assistant**:")
                        output.append(text)
                        output.append("")

                for tc in tool_calls_in_msg:
                    total_tool_calls += 1
                    name = tc.get("name", "unknown")
                    args = tc.get("arguments", {})
                    arg_summary = _summarize_args(name, args)
                    output.append(f"**Tool call: `{name}`** {arg_summary}")
                    output.append("")

            elif role == "toolResult":
                is_error = msg.get("isError", False)
                if is_error:
                    total_tool_errors += 1
                name = msg.get("toolName", "unknown")
                status = "❌ error" if is_error else "✓"
                output.append(f"**Result: `{name}`** {status}")

                for item in content:
                    text = item.get("text", "")
                    if text.strip():
                        cleaned = _clean_text(text)
                        if len(cleaned) > 2000:
                            cleaned = cleaned[:1997] + "..."
                        output.append("```")
                        output.append(cleaned)
                        output.append("```")
                output.append("")

    # Summary section
    output.append("---")
    output.append("")
    output.append("## Session Summary")
    output.append("")
    output.append("| Metric | Value |")
    output.append("|---|---|")
    output.append(f"| Turns | {len(turns)} |")
    output.append(f"| Input tokens | {total_input} |")
    output.append(f"| Output tokens | {total_output} |")
    output.append(f"| Cache read tokens | {total_cache_read} |")
    output.append(f"| Tool calls | {total_tool_calls} |")
    output.append(f"| Tool errors | {total_tool_errors} |")

    return "\n".join(output)


def _summarize_args(tool_name: str, args: Any) -> str:
    """Extract key arguments for display."""
    if not isinstance(args, dict):
        return ""
    if tool_name == "read":
        return f"`{args.get('path', '?')}`"
    elif tool_name == "edit":
        edits = args.get("edits", [])
        if isinstance(edits, list):
            ops = [e.get("op", "?") for e in edits if isinstance(e, dict)]
        else:
            ops = []
        return f"`{args.get('path', '?')}` ({', '.join(ops)})"
    elif tool_name == "bash":
        cmd = args.get("command", "")
        return f"`{cmd[:80]}`"
    elif tool_name == "write":
        return f"`{args.get('path', '?')}`"
    elif tool_name == "grep":
        return f"`{args.get('pattern', '?')}`"
    return ""
