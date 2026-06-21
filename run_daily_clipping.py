from __future__ import annotations

import argparse
from datetime import date
from zoneinfo import ZoneInfo
from datetime import datetime

from app import generate_daily_clipping


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily sector clippings.")
    parser.add_argument(
        "--date",
        default="",
        help="Clip date in YYYY-MM-DD. Defaults to today in Asia/Seoul.",
    )
    parser.add_argument(
        "--sectors",
        default="반도체,조선",
        help="Comma-separated sectors. Supported: 반도체, 조선.",
    )
    parser.add_argument("--max-items", type=int, default=15)
    args = parser.parse_args()

    if args.date:
        clip_date = date.fromisoformat(args.date)
    else:
        clip_date = datetime.now(ZoneInfo("Asia/Seoul")).date()

    for sector in [item.strip() for item in args.sectors.split(",") if item.strip()]:
        print(f"Generating {clip_date.isoformat()} {sector} clipping...")
        generate_daily_clipping(sector, clip_date, args.max_items)
        print(f"Done: {sector}")


if __name__ == "__main__":
    main()
