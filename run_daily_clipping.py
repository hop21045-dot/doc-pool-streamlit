from __future__ import annotations

import argparse
import os

from app import collect_saved_messages, collect_spot_price_posts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update heart-marked Telegram saved items and semiconductor spot prices."
    )
    parser.add_argument(
        "--saved-limit",
        type=int,
        default=int(os.getenv("SAVED_DAILY_LIMIT", "500")),
        help="Number of recent posts to inspect in saved source channels.",
    )
    parser.add_argument(
        "--include-all-saved-source-posts",
        action="store_true",
        help="Save every post from SAVED_SOURCE_CHANNELS instead of only heart-marked posts.",
    )
    parser.add_argument(
        "--spot-price-limit",
        type=int,
        default=int(os.getenv("SPOT_PRICE_DAILY_LIMIT", "30")),
        help="Number of recent semiconductor spot-price posts to collect.",
    )
    parser.add_argument("--skip-saved", action="store_true")
    parser.add_argument("--skip-spot-prices", action="store_true")
    args = parser.parse_args()

    if not args.skip_saved:
        print("Collecting heart-marked Telegram saved items...")
        count = collect_saved_messages(
            limit=args.saved_limit,
            include_heart_reactions=not args.include_all_saved_source_posts,
        )
        print(f"Done: saved items ({count} posts)")

    if not args.skip_spot_prices:
        print("Collecting semiconductor spot prices...")
        count = collect_spot_price_posts(limit=args.spot_price_limit, parse_images=True)
        print(f"Done: semiconductor spot prices ({count} posts)")


if __name__ == "__main__":
    main()
