"""CLI entrypoint for edit-benchmark."""

import argparse
import json
import sys
from pathlib import Path

from .runner import run_group, GroupResult


def find_extensions(ext_dir: Path) -> list[Path]:
    """Find all edit schema extensions in the extensions directory."""
    if not ext_dir.exists():
        return []
    extensions = []
    for d in sorted(ext_dir.iterdir()):
        if d.is_dir():
            index = d / "index.ts"
            if index.exists():
                extensions.append(index)
    return extensions


def find_test_groups(groups_dir: Path) -> list[Path]:
    """Find all test groups in the groups directory."""
    if not groups_dir.exists():
        return []
    return sorted(
        [d for d in groups_dir.iterdir() if d.is_dir()]
    )


def print_result(result: GroupResult, verbose: bool = False) -> None:
    """Print a single group result."""
    status = "PASS" if result.passed else "FAIL"
    print(f"\n  [{status}] {result.group_name} ({result.schema_name})")
    print(f"    Attempts: {result.total_attempts}")
    print(f"    Context tokens (1x): {result.context_tokens}")
    print(f"    Cost score: {result.cost_score}")
    print(f"    Turns: {result.total_turns}")


    if verbose:
        for step in result.steps:
            step_status = "PASS" if step.passed else "FAIL"
            metrics_str = ""
            if step.metrics:
                m = step.metrics.summary()
                metrics_str = f" | turns={m['turns']} ctx={m['context_tokens']} cost={m['cost_score']} errors={m['tool_errors']}"
            print(f"      {step_status} {step.step_name} ({step.attempts} attempt(s)){metrics_str}")
            if step.failures:
                for failure in step.failures:
                    print(f"        FAIL: {failure}")


def generate_json_report(
    results: list[GroupResult],
    output_path: Path,
) -> None:
    """Generate a JSON report from benchmark results."""
    report = {
        "summary": {
            "total_groups": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
        },
        "results": [],
    }

    for r in results:
        entry = {
            "group": r.group_name,
            "schema": r.schema_name,
            "passed": r.passed,
            "attempts": r.total_attempts,
            "context_tokens": r.context_tokens,
            "cost_score": r.cost_score,
            "turns": r.total_turns,
            "steps": [],
        }
        for s in r.steps:
            step_entry = {
                "name": s.step_name,
                "passed": s.passed,
                "attempts": s.attempts,
            }
            if s.metrics:
                step_entry["metrics"] = s.metrics.summary()
            if s.failures:
                step_entry["failures"] = s.failures
            entry["steps"].append(step_entry)
        report["results"].append(entry)

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark LLM coding agent edit tool schemas",
    )
    parser.add_argument(
        "--extensions-dir",
        default="extensions",
        help="Directory containing edit schema extensions (default: extensions/)",
    )
    parser.add_argument(
        "--groups-dir",
        default="groups",
        help="Directory containing test groups (default: groups/)",
    )
    parser.add_argument(
        "--workspace",
        default="workspace",
        help="Workspace directory for benchmark runs (default: workspace/)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries per step on validation failure (default: 3)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show per-step details",
    )
    parser.add_argument(
        "--json-report",
        help="Write JSON report to this file",
    )
    args = parser.parse_args()

    project_root = Path.cwd()
    ext_dir = project_root / args.extensions_dir
    groups_dir = project_root / args.groups_dir
    workspace_base = project_root / args.workspace

    extensions = find_extensions(ext_dir)
    groups = find_test_groups(groups_dir)

    if not extensions:
        print(f"ERROR: No extensions found in {ext_dir}", file=sys.stderr)
        sys.exit(1)

    if not groups:
        print(f"ERROR: No test groups found in {groups_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Extensions: {len(extensions)}")
    for e in extensions:
        print(f"  - {e.parent.name}")
    print(f"Test groups: {len(groups)}")
    for g in groups:
        print(f"  - {g.name}")
    print(f"Workspace: {workspace_base}")
    print()

    all_results: list[GroupResult] = []

    total = len(extensions) * len(groups)
    current = 0

    for ext_path in extensions:
        schema_name = ext_path.parent.name
        print(f"=== Schema: {schema_name} ===")

        for group_dir in groups:
            current += 1
            label = f"[{current}/{total}]"
            print(f"{label} Running {group_dir.name} with {schema_name}...", end="", flush=True)

            result = run_group(
                workspace_base=workspace_base,
                group_dir=group_dir,
                extension_path=ext_path,
                max_retries=args.max_retries,
            )
            all_results.append(result)
            print_result(result, verbose=args.verbose)

    # Summary
    passed = sum(1 for r in all_results if r.passed)
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{len(all_results)} groups passed")

    # Per-schema summary
    print(f"\n{'Schema':<25} {'Passed':<8} {'Context':<10} {'Cost':<10} {'Turns':<8}")
    print("-" * 65)

    schema_results: dict[str, list[GroupResult]] = {}
    for r in all_results:
        schema_results.setdefault(r.schema_name, []).append(r)

    for schema_name, results in schema_results.items():
        p = sum(1 for r in results if r.passed)
        total_ctx = sum(r.context_tokens for r in results)
        total_cost = sum(r.cost_score for r in results)
        total_turns = sum(r.total_turns for r in results)
        n = len(results)
        avg_ctx = total_ctx / n if n > 0 else 0
        avg_cost = total_cost / n if n > 0 else 0
        avg_turns = total_turns / n if n > 0 else 0
        print(f"{schema_name:<25} {p}/{n:<6} {avg_ctx:>8.0f}  {avg_cost:>8.0f}  {avg_turns:>6.1f}")

    if args.json_report:
        generate_json_report(all_results, Path(args.json_report))
        print(f"\nJSON report written to {args.json_report}")


if __name__ == "__main__":
    main()
