"""Warehouse inventory module — exercises distributed renames."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class InventoryItem:
    sku: str
    name: str
    quantity: int
    location: str


MAX_ITEMS = 10_000
"""Maximum number of items that can be stored at once."""

MAX_BATCH = 250
"""Maximum items to retrieve in a single batch operation."""


def process_item(item: InventoryItem) -> InventoryItem:
    """Process a single inventory item: normalize name and validate location.

    This is the core processing function used throughout the warehouse.
    Every item passes through process_item before being stored or retrieved.
    """
    item.name = item.name.strip().lower()
    if not item.location:
        item.location = "A1-DEFAULT"
    return item


class ItemProcessor:
    """Handles batch operations on inventory items using process_item."""

    def __init__(self, max_batch: int = MAX_BATCH):
        self.max_batch = max_batch
        self.processed_count = 0

    def run_batch(self, items: list[InventoryItem]) -> list[InventoryItem]:
        """Process a batch of items through process_item."""
        batch = items[: self.max_batch]
        result = []
        for item in batch:
            item = process_item(item)
            result.append(item)
            self.processed_count += 1
        return result

    def reset(self) -> None:
        """Reset the processed count for this ItemProcessor."""
        self.processed_count = 0


def ingest_items(raw_items: list[dict]) -> list[InventoryItem]:
    """Convert raw dicts into InventoryItem objects and process them."""
    result: list[InventoryItem] = []
    for raw in raw_items:
        item = InventoryItem(
            sku=raw.get("sku", ""),
            name=raw.get("name", ""),
            quantity=raw.get("quantity", 0),
            location=raw.get("location", ""),
        )
        # Use process_item for normalization
        item = process_item(item)
        result.append(item)
        if len(result) >= MAX_ITEMS:
            break
    return result


def search_by_name(items: list[InventoryItem], query: str) -> list[InventoryItem]:
    """Find items whose name contains the query string.

    Each matching item is run through process_item to normalize before return.
    """
    matching: list[InventoryItem] = []
    for item in items:
        if query.lower() in item.name.lower():
            item = process_item(item)
            matching.append(item)
    return matching


def transfer_item(
    item: InventoryItem,
    new_location: str,
    processor: Optional[ItemProcessor] = None,
) -> InventoryItem:
    """Transfer an item to a new location, re-processing it."""
    item.location = new_location
    # Re-run process_item to ensure consistency
    item = process_item(item)
    if processor is not None:
        processor.run_batch([item])
    return item


def bulk_restock(
    items: list[InventoryItem],
    quantity_delta: int,
) -> list[InventoryItem]:
    """Add quantity to all items in a list, then re-process.

    Uses process_item after updating to ensure validity.
    Capped by MAX_ITEMS to prevent overflow.
    """
    result: list[InventoryItem] = []
    for item in items[:MAX_ITEMS]:
        item.quantity += quantity_delta
        item = process_item(item)
        result.append(item)
    return result
