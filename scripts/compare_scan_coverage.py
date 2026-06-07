"""Compare storage-layer scan coverage across all Confluence spaces.

Prints per-space statistics:
  - total_pages_in_space : all pages returned by the storage API (full scan cost)
  - filtered_count       : pages whose last_modified >= since_date (what we process)
  - scan_ratio           : filtered / total (efficiency of the date window)

This is useful for understanding the difference between the old CQL approach
(which returned only matching pages directly but suffered from search-index gaps)
and the new storage-layer approach (which must scan every page locally).

Usage:
    PYTHONPATH=src python scripts/compare_scan_coverage.py [--days N] [--space KEY]

Options:
    --days N      Look-back window in days (default: 60)
    --space KEY   Restrict scan to a single space key (optional)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Bootstrap path so we can import from src/
# ---------------------------------------------------------------------------
sys.path.insert(0, "src")

from connectors.producers.confluence.confluence_config import (
    create_confluence_connection,
    load_config_from_file,
)
from connectors.producers.confluence.confluence_helpers import _parse_last_modified
from connectors.producers.confluence.fetch_spaces import fetch_spaces
from common.logger import logger


def _scan_space(
    confluence: Any,
    space_key: str,
    since_date: datetime,
    page_size: int = 50,
) -> Dict[str, Any]:
    """Scan one space and return raw counts without date filtering."""
    total_scanned = 0
    filtered_count = 0

    for content_type in ("page", "blogpost"):
        start = 0
        while True:
            response = confluence.get(
                f"/rest/api/space/{space_key}/content/{content_type}",
                params={
                    "expand": "version",
                    "limit": page_size,
                    "start": start,
                },
            )
            if not isinstance(response, dict):
                break
            batch = response.get("results", [])
            if not batch:
                break

            total_scanned += len(batch)
            for item in batch:
                last_mod = _parse_last_modified(item)
                if last_mod is None or last_mod >= since_date:
                    filtered_count += 1

            start += len(batch)
            if len(batch) < page_size:
                break

    return {
        "space_key": space_key,
        "total_scanned": total_scanned,
        "filtered_count": filtered_count,
        "scan_ratio": (filtered_count / total_scanned) if total_scanned else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=60, help="Look-back window in days (default: 60)")
    parser.add_argument("--space", type=str, default=None, help="Restrict to a single space key")
    args = parser.parse_args()

    since_date = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"Since date : {since_date.isoformat()}")
    print(f"Look-back  : {args.days} days")
    print()

    config = load_config_from_file()
    accounts = config.get("account", [])
    if not accounts:
        print("No Confluence accounts configured.")
        sys.exit(1)

    account = accounts[0]
    confluence = create_confluence_connection({"account": [account]})

    if args.space:
        spaces = [{"key": args.space.upper()}]
    else:
        print("Fetching space list...")
        spaces = fetch_spaces(confluence)
        print(f"Found {len(spaces)} spaces.\n")

    header = f"{'Space':<45} {'Total':>8} {'Filtered':>10} {'Ratio':>8}"
    print(header)
    print("-" * len(header))

    grand_total = 0
    grand_filtered = 0

    for space in spaces:
        key = (space.get("key") or "").strip().upper()
        if not key:
            continue

        stats = _scan_space(confluence, key, since_date)
        grand_total += stats["total_scanned"]
        grand_filtered += stats["filtered_count"]

        ratio_pct = f"{stats['scan_ratio'] * 100:.1f}%"
        print(f"{key:<45} {stats['total_scanned']:>8} {stats['filtered_count']:>10} {ratio_pct:>8}")

    print("-" * len(header))
    grand_ratio = f"{(grand_filtered / grand_total * 100):.1f}%" if grand_total else "n/a"
    print(f"{'TOTAL':<45} {grand_total:>8} {grand_filtered:>10} {grand_ratio:>8}")
    print()
    print(f"Pages that need processing : {grand_filtered}")
    print(f"Pages scanned to find them : {grand_total}")
    if grand_total:
        print(f"Overhead factor            : {grand_total / grand_filtered:.1f}x" if grand_filtered else "Overhead factor: inf (nothing in window)")


if __name__ == "__main__":
    main()
