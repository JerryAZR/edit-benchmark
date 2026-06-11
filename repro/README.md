# pi --session bug: blank lines in prompt + non-TTY = lost session

## Trigger

When pi is spawned via `subprocess.run` with all stdio redirected to DEVNULL
(no TTY), **and** the `-p` prompt contains a blank line (`\n\n`), pi completes
successfully (exit 0, edits correct) but does NOT write the `--session` file.

This does NOT happen when running from an interactive shell (TTY).

## Setup

```bash
mkdir -p repro/src
echo 'version = "1.0.0"' > repro/src/single.py

# prompt-ok.txt: single paragraph, no blank lines
cat > repro/prompt-ok.txt << 'EOF'
Edit src/single.py. Change the version from 1.0.0 to 2.0.0-beta1.
EOF

# prompt-bug.txt: same text, blank line before extra sentence
cat > repro/prompt-bug.txt << 'EOF'
Edit src/single.py. Change the version from 1.0.0 to 2.0.0-beta1.

The file should still have exactly one line.
EOF
```

## Reproduction (Python subprocess, non-TTY)

```python
import subprocess
from pathlib import Path

cwd = str(Path('repro').resolve())

# OK: session written
prompt = Path('repro/prompt-ok.txt').read_text().strip()
ses = Path('repro/session-ok.jsonl').resolve()
subprocess.run(
    ['pi.cmd', '-p', prompt, '--model', 'deepseek-v4-flash', '--session', str(ses)],
    cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL, timeout=30)
assert ses.exists()  # passes

# BUG: session NOT written despite rc=0 and successful edit
prompt = Path('repro/prompt-bug.txt').read_text().strip()
ses = Path('repro/session-bug.jsonl').resolve()
subprocess.run(
    ['pi.cmd', '-p', prompt, '--model', 'deepseek-v4-flash', '--session', str(ses)],
    cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL, timeout=30)
assert ses.exists()  # FAILS
```

## What DOESN'T trigger it

- Running from an interactive shell (both prompts write session)
- `capture_output=True` instead of DEVNULL (same behavior)
- Quotes, colons, or prompt length in the text
- Any particular file type or edit operation
- Extension loading or model selection

## What DOES trigger it

- `stdin/stdout/stderr` all redirected away from a TTY (Python subprocess)
- `\n\n` (blank line / paragraph break) present in the `-p` prompt text
- Both conditions must be true simultaneously
