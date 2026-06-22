from __future__ import annotations

import argparse
import os
from datetime import date
from zoneinfo import ZoneInfo
from datetime import datetime

from app import collect_spot_price_posts, generate_daily_clipping


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
    parser.add_argument(
        "--spot-price-limit",
        type=int,
        default=int(os.getenv("SPOT_PRICE_DAILY_LIMIT", "30")),
        help="Number of recent semiconductor spot price posts to collect.",
    )
    parser.add_argument("--skip-spot-prices", action="store_true")
    args = parser.parse_args()

    if args.date:
        clip_date = date.fromisoformat(args.date)
    else:
        clip_date = datetime.now(ZoneInfo("Asia/Seoul")).date()

    for sector in [item.strip() for item in args.sectors.split(",") if item.strip()]:
        print(f"Generating {clip_date.isoformat()} {sector} clipping...")
        generate_daily_clipping(sector, clip_date, args.max_items)
        print(f"Done: {sector}")

    if not args.skip_spot_prices:
        print("Collecting semiconductor spot prices...")
        count = collect_spot_price_posts(limit=args.spot_price_limit, parse_images=True)
        print(f"Done: semiconductor spot prices ({count} posts)")


if __name__ == "__main__":
    main()
