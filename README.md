# edit-benchmark

Benchmark suite for evaluating edit tool schemas used by LLM coding agents.

Compares different edit tool interfaces across multi-step editing scenarios,
measuring token usage, cost, turn counts, and edit accuracy.

## How it works

```
edit-benchmark (Python, outside pi)
│
├── For each edit schema extension:
│   └── For each test group:
│       ├── Run N times (--runs), each in an isolated workspace
│       │   ├── cp initial/ → workspace/{group}-{schema}/run-{N}/
│       │   └── For each step:
│       │       ├── node cli.js -p "instruction" -e extension --session session.jsonl
│       │       ├── validate (assertion-based, lenient)
│       │       └── retry on failure (until timeout)
│       │
│       └── Parse per-run session JSONL → token usage, turns, tool calls
│
└── Average across runs → summary table
```

## Project structure

```
edit-benchmark/
├── extensions/           # Edit schema extensions (YOU provide these)
│   ├── empty1/index.ts   # Placeholder for flow testing
│   └── empty2/index.ts   # Placeholder for flow testing
├── groups/               # Test scenarios (7 groups)
│   ├── api-refactor/     # Small multi-step edits (smoke test)
│   ├── ambiguous-text/   # 5 identical-looking functions
│   ├── boundary/         # Empty file, single-line, EOF edits
│   ├── indentation/      # Nest/un-nest Python blocks
│   ├── special-chars/    # Source with regex metacharacters
│   ├── large-edits/      # Add/delete/rewrite large blocks
│   └── distributed-rename/ # Rename identifiers (8-11 occurrences)
├── src/edit_benchmark/   # Python harness
│   ├── cli.py            # Entry point
│   ├── runner.py         # Orchestrator
│   ├── session_parser.py # Parse pi session JSONL
│   └── validator.py      # Assertion-based validation
├── repro/                # Bug reproduction (Windows pi.cmd wrapper)
└── pyproject.toml
```

## Getting started

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
pip install -e .
```

### 2. Provide edit schema extensions

The benchmark needs **real** edit schema extensions — published pi packages that shadow
`read` and `edit` with different interfaces. Drop them in `extensions/`:

```
extensions/
├── edit-hashline/index.ts    # LINE#HASH anchored edits
├── edit-textreplace/index.ts # oldText/newText exact replacement
├── edit-linenumber/index.ts  # Line-number based
├── edit-regex/index.ts       # Regex-based
└── edit-diff/index.ts        # Unified diff patch
```

Each extension shadows pi's built-in `read` and `edit` tools (pi supports this via
`pi.registerTool({ name: "read", ... })`).

**The empty1/empty2 placeholders are for flow testing only** — they produce meaningful
metric shapes (tokens, turns) but don't test different edit schemas.

### 3. Run

```bash
edit-benchmark --model deepseek-v4-flash --verbose
```

Or without activating:

```bash
.venv/Scripts/python -m edit_benchmark.cli --model deepseek-v4-flash
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--extensions-dir` | `extensions/` | Path to edit schema extensions |
| `--groups-dir` | `groups/` | Path to test groups |
| `--workspace` | `workspace/` | Working directory for runs |
| `--model` | `deepseek-v4-flash` | Model passed to pi |
| `--runs` | `1` | Runs per (schema, group) for averaging |
| `--timeout` | `600` | Total timeout per run in seconds |
| `--verbose`, `-v` | off | Show per-step and per-run details |
| `--json-report` | none | Write JSON report to file |

## Test group format

Each test group is a directory under `groups/`:

```
groups/my-test/
├── initial/                    # Starting files (copied to workspace)
│   └── src/
│       └── main.py
├── step-1-description/
│   ├── instruction.md          # Prompt for the agent
│   └── validate.yaml           # Assertions to check
├── step-2-description/
│   ├── instruction.md
│   └── validate.yaml
└── step-3-description/
    ├── instruction.md
    └── validate.yaml
```

Steps run sequentially in the **same session** (and workspace). Step 2 sees step 1's
edits. If a step times out, the entire run is discarded. If a step fails validation,
it retries with the error message as feedback — until it passes or the run times out.

### validate.yaml format

```yaml
# Single file mode
file: src/main.py
must_contain:
  - pattern1           # Regex: must be found in file
  - pattern2
must_not_contain:
  - bad-pattern        # Regex: must NOT be found in file

# Multi-file mode
files:
  src/main.py:
    must_contain:
      - "def new_function"
  src/utils.py:
    must_not_contain:
      - "old import"
```

Patterns are Python regex. Use single-quoted YAML strings for metacharacters:

```yaml
must_contain:
  - 'response\.json\(\)'
  - '(?m)^    def outer'    # Anchored to line start
```

Assertions are **semantic, not byte-level** — patterns check for keywords/structures,
not exact formatting. This tolerates LLM creativity (extra comments, reformatting, etc.).

### Metrics

| Metric | Source | Meaning |
|--------|--------|---------|
| **Context tokens** | Last turn's `cacheRead + input + output` | Total unique tokens in conversation (once-counted) |
| **Cost score** | Σ(cacheRead×1 + input×10 + output×40) | Weighted cost (lower = cheaper) |
| **Turns** | Assistant message count | Agent reasoning + tool call rounds |
| **Tool errors** | `isError` flags in session | Rejected or failed edits |

## Test coverage

| Pattern | Group | What |
|---------|-------|------|
| Small addition | api-refactor, boundary, ambiguous-text | 1-3 line insertions |
| Small deletion | special-chars | Remove single line |
| Small replacement | boundary | Change version string |
| Large addition (15+ lines) | large-edits | New function between existing ones |
| Large deletion | large-edits | Delete entire 20-line function |
| Large rewrite | large-edits | Replace function body completely |
| Distributed rename (10+ occurrences) | distributed-rename | Function, class, constants |
| Re-indentation / nesting | indentation | Nested try/except, class wrapping |
| Empty file edit | boundary | Write into 0-byte file |
| EOF edit | boundary | Change last line |
| Ambiguous matches | ambiguous-text | 5 identical-looking functions |
| Regex metacharacters in source | special-chars | Patterns with `.*?+[]()` etc. |
| Non-contiguous edits | boundary | First + last line simultaneously |

## License

MIT
