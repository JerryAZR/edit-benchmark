"""Data pipeline module — exercises large-scale edit operations."""

import json
import os
from typing import Any


def load_config(path: str) -> dict[str, Any]:
    """Load pipeline configuration from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_record(record: dict[str, Any]) -> list[str]:
    """Check a data record for required fields and type correctness.

    Returns a list of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

    if not isinstance(record, dict):
        return ["Record must be a dictionary"]

    required = {"id", "name", "timestamp"}
    missing = required - set(record.keys())
    if missing:
        errors.append(f"Missing required fields: {', '.join(sorted(missing))}")

    if "id" in record and not isinstance(record["id"], str):
        errors.append("Field 'id' must be a string")

    if "name" in record and not isinstance(record["name"], str):
        errors.append("Field 'name' must be a string")

    if "timestamp" in record and not isinstance(record["timestamp"], (int, float)):
        errors.append("Field 'timestamp' must be a number")

    return errors


def filter_records(
    records: list[dict[str, Any]],
    min_timestamp: float = 0.0,
    max_timestamp: float | None = None,
) -> list[dict[str, Any]]:
    """Filter records by timestamp range.

    Args:
        records: List of data records with 'timestamp' field.
        min_timestamp: Inclusive lower bound (default 0).
        max_timestamp: Inclusive upper bound (None = no upper bound).

    Returns:
        Records whose timestamp falls within [min, max].
    """
    result: list[dict[str, Any]] = []

    for record in records:
        ts = record.get("timestamp", 0)
        if ts < min_timestamp:
            continue
        if max_timestamp is not None and ts > max_timestamp:
            continue
        result.append(record)

    return result


def deduplicate_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate records based on the 'id' field.

    First occurrence is kept; subsequent duplicates are dropped.
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []

    for record in records:
        rid = record.get("id", "")
        if rid and rid not in seen:
            seen.add(rid)
            result.append(record)

    return result


def batch_process(
    records: list[dict[str, Any]],
    batch_size: int = 100,
    output_dir: str = "output",
) -> int:
    """Process records in batches, writing each batch to a JSON file.

    Each batch file is named batch_001.json, batch_002.json, etc.

    Returns:
        Total number of records processed.
    """
    os.makedirs(output_dir, exist_ok=True)
    total_processed = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        filename = os.path.join(output_dir, f"batch_{batch_num:03d}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2)
        total_processed += len(batch)

    return total_processed
