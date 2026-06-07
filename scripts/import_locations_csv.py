"""Import Chernivtsi locations from a CSV file.

Idempotent: locations are matched by exact name and skipped if they already
exist.

Usage:
    uv run python -m scripts.import_locations_csv --csv "C:\\path\\locations.csv"
    uv run python -m scripts.import_locations_csv --csv "C:\\path\\locations.csv" --dry-run
"""

import argparse
import asyncio
import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from guidloc.common.database import async_session_factory
from guidloc.common.logging import setup_logging
from guidloc.locations.models import Location, LocationCategory, PriceLevel
from guidloc.locations.schemas import LocationCreate
from guidloc.locations.service import create_location

logger = logging.getLogger(__name__)

COORDINATE_PRECISION = 6


CATEGORY_MAP: dict[str, LocationCategory] = {
    "restaurant": LocationCategory.RESTAURANT,
    "shop": LocationCategory.SHOP,
    "cafe": LocationCategory.CAFE,
    "bar": LocationCategory.BAR,
    "entertainment": LocationCategory.ENTERTAINMENT,
    "supermarket": LocationCategory.SHOP,
    "beauty": LocationCategory.SHOP,
}

PRICE_LEVEL_MAP: dict[str, PriceLevel] = {
    "budget": PriceLevel.LOW,
    "low": PriceLevel.LOW,
    "moderate": PriceLevel.MEDIUM,
    "medium": PriceLevel.MEDIUM,
    "expensive": PriceLevel.HIGH,
    "high": PriceLevel.HIGH,
    "free": PriceLevel.FREE,
}


@dataclass
class ImportSummary:
    created: int = 0
    skipped_existing: int = 0
    skipped_invalid: int = 0
    inactive_imported: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import locations from a CSV file.")
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Path to the source CSV file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report changes without writing to the database.",
    )
    return parser.parse_args()


def clean(value: str | None) -> str:
    return (value or "").strip()


def parse_tags(value: str | None) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []

    for raw_tag in clean(value).split(";"):
        tag = raw_tag.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)

    return tags


def parse_category(value: str | None) -> LocationCategory:
    category = CATEGORY_MAP.get(clean(value).lower())
    return category or LocationCategory.OTHER


def parse_price_level(value: str | None) -> PriceLevel | None:
    normalized = clean(value).lower()
    if not normalized or normalized == "unknown":
        return None
    return PRICE_LEVEL_MAP.get(normalized)


def build_location_payload(row: dict[str, Any]) -> LocationCreate:
    name = clean(row.get("name"))
    latitude = round(float(clean(row.get("latitude"))), COORDINATE_PRECISION)
    longitude = round(float(clean(row.get("longitude"))), COORDINATE_PRECISION)
    description = clean(row.get("full_description")) or clean(
        row.get("short_description")
    )

    return LocationCreate(
        name=name,
        description=description,
        address=clean(row.get("address_text")),
        latitude=latitude,
        longitude=longitude,
        category=parse_category(row.get("location_type")),
        price_level=parse_price_level(row.get("price_level")),
        tags=parse_tags(row.get("tags")),
        is_active=clean(row.get("status")).lower() == "active",
    )


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


async def import_locations(csv_path: Path, *, dry_run: bool) -> ImportSummary:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {csv_path}")

    rows = load_rows(csv_path)
    summary = ImportSummary()

    async with async_session_factory() as session:
        for row_number, row in enumerate(rows, start=2):
            try:
                payload = build_location_payload(row)
            except (TypeError, ValueError, ValidationError) as error:
                summary.skipped_invalid += 1
                logger.warning("Skipping row %d: %s", row_number, error)
                continue

            existing = await session.execute(
                select(Location).where(
                    Location.name == payload.name,
                    Location.latitude == round(payload.latitude, COORDINATE_PRECISION),
                    Location.longitude == round(payload.longitude, COORDINATE_PRECISION),
                )
            )
            if existing.scalar_one_or_none() is not None:
                summary.skipped_existing += 1
                continue

            if not dry_run:
                await create_location(session, payload)

            summary.created += 1
            if not payload.is_active:
                summary.inactive_imported += 1

    return summary


async def main() -> None:
    args = parse_args()
    setup_logging("INFO")

    summary = await import_locations(args.csv, dry_run=args.dry_run)
    action = "Dry run finished" if args.dry_run else "Import finished"
    logger.info(
        "%s: created=%d, skipped_existing=%d, skipped_invalid=%d, "
        "inactive_imported=%d",
        action,
        summary.created,
        summary.skipped_existing,
        summary.skipped_invalid,
        summary.inactive_imported,
    )


if __name__ == "__main__":
    asyncio.run(main())
