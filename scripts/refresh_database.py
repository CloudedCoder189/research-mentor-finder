from __future__ import annotations

import argparse

from services.refresh import UNIVERSITY_SCRAPERS, refresh_university


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh professor records from official sources.")
    parser.add_argument(
        "university",
        choices=list(UNIVERSITY_SCRAPERS),
        help="University source to refresh",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit records/profiles for testing")
    parser.add_argument("--openai", action="store_true", help="Use OpenAI for topic labels")
    args = parser.parse_args()

    summary = refresh_university(
        args.university,
        use_openai=args.openai,
        max_profiles=args.limit,
        progress_callback=print,
    )
    print(summary)


if __name__ == "__main__":
    main()
