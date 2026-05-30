#!/usr/bin/env python3
"""
Pre-collect papers into the shared database day by day.

This script is intended for building a reusable paper cache before running
historical simulations with --skip-paper-collection. It calls the existing
all-source collector once per day to avoid single-query source limits over
long date ranges.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.collect_all_papers import collect_all_papers

DB_PATH = PROJECT_ROOT / "data" / "paperflow.db"


def _parse_day(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d")


def _count_papers_for_day(day: datetime) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE publish_date = ?",
            (day.strftime("%Y-%m-%d"),),
        )
        return int(cursor.fetchone()[0])
    finally:
        conn.close()


def _count_total_papers() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM papers")
        return int(cursor.fetchone()[0])
    finally:
        conn.close()


def precollect_by_day(
    *,
    start_date: str,
    end_date: str,
    sources: Optional[List[str]],
    limit_per_source: Optional[int],
) -> None:
    start = _parse_day(start_date)
    end = _parse_day(end_date)
    if end < start:
        raise ValueError("--end-date must be >= --start-date")

    print(f"Pre-collecting papers from {start.date()} to {end.date()}")
    print(f"Sources: {sources or ['arxiv', 'openreview', 'journal']}")
    print(f"Limit per source: {limit_per_source if limit_per_source is not None else 'collector default'}")
    print(f"Initial DB papers: {_count_total_papers()}")

    current = start
    days = 0
    total_reported_new = 0
    while current <= end:
        day_key = current.strftime("%Y%m%d")
        day_label = current.strftime("%Y-%m-%d")
        before_day_count = _count_papers_for_day(current)
        print("\n" + "=" * 72)
        print(f"[{day_label}] collecting one-day paper cache")
        print(f"[{day_label}] existing papers for this date: {before_day_count}")

        reported_new = collect_all_papers(
            start_date=day_key,
            end_date=day_key,
            sources=sources,
            limit_per_source=limit_per_source,
        )

        after_day_count = _count_papers_for_day(current)
        print(
            f"[{day_label}] collector reported new={reported_new}; "
            f"date_count {before_day_count} -> {after_day_count}"
        )

        total_reported_new += int(reported_new or 0)
        days += 1
        current += timedelta(days=1)

    print("\n" + "=" * 72)
    print(f"Pre-collection complete: {days} days")
    print(f"Collector reported total new papers: {total_reported_new}")
    print(f"Final DB papers: {_count_total_papers()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-collect all-source papers day by day")
    parser.add_argument("--start-date", required=True, help="Start date YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="End date YYYYMMDD")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="Sources to collect, default: arxiv openreview journal",
    )
    parser.add_argument(
        "--limit-per-source",
        type=int,
        default=None,
        help="Optional per-source limit for each day. Omit for collector defaults.",
    )
    args = parser.parse_args()

    precollect_by_day(
        start_date=args.start_date,
        end_date=args.end_date,
        sources=args.sources,
        limit_per_source=args.limit_per_source,
    )


if __name__ == "__main__":
    main()
