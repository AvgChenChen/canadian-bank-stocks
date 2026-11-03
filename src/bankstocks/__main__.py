"""Build the report: python -m bankstocks [--refresh] [--end 2026-10] [--years 10]"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from .report import analyse, readme_section, update_readme, write_report
from .sources import load_policy_rate, load_prices
from .universe import BANKS, BENCHMARK, POLICY_RATE_SERIES

ROOT = Path(__file__).resolve().parents[2]


def last_complete_month(today: date) -> pd.Period:
    return pd.Period(today, freq="M") - 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end", help="last month to include, YYYY-MM (default: last complete month)")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--refresh", action="store_true", help="download again instead of using the cache")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--out", type=Path, default=ROOT / "report")
    args = parser.parse_args(argv)

    today = date.today()
    end = pd.Period(args.end, freq="M") if args.end else last_complete_month(today)
    start = end - 12 * args.years  # the month the $10,000 goes in, at the month-end close

    def prices(security):
        print(f"  {security.ticker:<8} {security.name}")
        return load_prices(security.ticker, start, end, args.data, args.refresh)

    print(f"Loading {start} to {end}:")
    banks = {s: prices(s) for s in BANKS}
    benchmark = (BENCHMARK, prices(BENCHMARK))
    rate = load_policy_rate(POLICY_RATE_SERIES, start, end, args.data, args.refresh)

    analysis = analyse(banks, benchmark, rate)
    path = write_report(analysis, args.out, today)
    print(f"Wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    readme = ROOT / "README.md"
    if readme.exists() and update_readme(readme, readme_section(analysis)):
        print("Updated the results section in README.md")


if __name__ == "__main__":
    main()
