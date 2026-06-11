"""Bracket-heavy module — exercises edits near deeply nested structures."""

from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class Config:
    name: str
    settings: dict[str, Any]
    children: list["Config"] | None = None


def process_config(config: Config) -> dict[str, Any]:
    """Walk a config tree and flatten it into a result dict.

    This function uses deeply nested blocks, multi-line closing brackets,
    and bracket-heavy expressions that are difficult for text-replace and
    diff-based schemas to handle correctly.
    """
    result: dict[str, Any] = {}

    # Outer loop: iterate through settings
    for key, value in config.settings.items():
        normalized_key = key.strip().lower()

        # Level 1: type-based branching
        if isinstance(value, dict):
            # Level 2: nested dict processing
            for sub_key, sub_value in value.items():
                full_key = f"{normalized_key}.{sub_key}"

                # Level 3: value type dispatch
                if isinstance(sub_value, (int, float)):
                    if sub_value < 0:
                        result[full_key] = abs(sub_value)
                    else:
                        if sub_value > 1000:
                            result[full_key] = sub_value // 2
                        else:
                            result[full_key] = sub_value * 2
                elif isinstance(sub_value, str):
                    # Level 4: string processing with nested call
                    cleaned = sub_value.strip().replace(
                        "\n", " "
                    ).replace(
                        "\t", "    "
                    )
                    if len(cleaned) > 100:
                        result[full_key] = cleaned[:97] + "..."
                    else:
                        result[full_key] = cleaned
                elif isinstance(sub_value, list):
                    # Level 4: list processing
                    filtered = [
                        item
                        for item in sub_value
                        if item is not None
                    ]
                    if len(filtered) > 10:
                        result[full_key] = filtered[:10]
                    else:
                        result[full_key] = filtered
                else:
                    result[full_key] = str(sub_value)

        elif isinstance(value, list):
            # Level 2: list with comprehension
            processed = [
                (
                    item["id"],
                    item.get(
                        "metadata",
                        {"source": "unknown", "priority": 0}
                    )["priority"]
                )
                for item in value
                if isinstance(item, dict) and "id" in item
            ]
            result[normalized_key] = dict(processed)

        elif isinstance(value, str):
            # Level 2: build a query-like structure
            parts = value.split(".")
            if len(parts) > 1:
                result[normalized_key] = {
                    "root": parts[0],
                    "path": ".".join(parts[1:]),
                    "depth": len(parts) - 1
                }
            else:
                result[normalized_key] = value

        else:
            # Fallback
            result[normalized_key] = value

    # Traverse children recursively
    if config.children:
        for i, child in enumerate(config.children):
            child_result = process_config(child)
            for ck, cv in child_result.items():
                result[f"child[{i}].{ck}"] = cv

    return result


SAMPLE_CONFIG = Config(
    name="root",
    settings={
        "database": {
            "host": "localhost",
            "port": 5432,
            "pool": {
                "min": 1,
                "max": 10,
                "timeout": 30
            },
            "backups": [
                {"day": "mon", "time": "02:00", "retention": 7},
                {"day": "thu", "time": "03:00", "retention": 30}
            ]
        },
        "cache": {
            "ttl": 300,
            "strategy": "lru",
            "endpoints": [
                "redis://localhost:6379/0",
                "redis://localhost:6379/1"
            ]
        },
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "handlers": ["console", "file"]
        }
    },
    children=[
        Config(name="sub1", settings={"enabled": True, "threshold": 0.75}),
        Config(name="sub2", settings={"enabled": False, "threshold": 0.90}),
    ]
)
