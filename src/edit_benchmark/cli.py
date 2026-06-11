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
    runs_info = f" ({result.runs_completed}/{result.runs_total} runs)" if result.runs_total > 1 else ""
    print(f"\n  [{status}] {result.group_name} ({result.schema_name}){runs_info}")
    print(f"    Context tokens (avg): {result.context_tokens}")
    print(f"    Cost score (avg):     {result.cost_score}")
    print(f"    Turns (avg):          {result.total_turns:.1f}")

    if verbose:
        for run in result.runs:
            run_status = "PASS" if run.passed else "FAIL"
            m = run.metrics
            if m:
                print(f"    run: {run_status} ctx={m.context_tokens} cost={m.cost_score} turns={m.turn_count}")
            else:
                print(f"    run: {run_status}")
            for s in run.steps:
                s_status = "PASS" if s.passed else "FAIL"
                print(f"      {s_status} {s.step_name} ({s.attempts} attempt(s))")
                if s.failures:
                    for failure in s.failures:
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
            "runs_completed": r.runs_completed,
            "runs_total": r.runs_total,
            "context_tokens_avg": r.context_tokens,
            "cost_score_avg": r.cost_score,
            "turns_avg": r.total_turns,
            "runs": [],
        }
        for run in r.runs:
            run_entry = {
                "passed": run.passed,
                "metrics": run.metrics.summary() if run.metrics else None,
                "steps": [
                    {
                        "name": s.step_name,
                        "passed": s.passed,
                        "attempts": s.attempts,
                        "failures": s.failures,
                    }
                    for s in run.steps
                ],
            }
            entry["runs"].append(run_entry)
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
        "--runs",
        type=int,
        default=1,
        help="Number of runs per (extension, group) for averaging (default: 1)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Total timeout per run in seconds (default: 600)",
    )
    parser.add_argument(
        "--model",
        default="deepseek-v4-flash",
        help="Model to use for pi (default: deepseek-v4-flash)",
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
    if args.runs > 1:
        print(f"Runs per group: {args.runs}")
        print(f"Timeout per run: {args.timeout}s")
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
                runs=args.runs,
                timeout=args.timeout,
                model=args.model,
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
