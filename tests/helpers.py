"""Build small, hand-checkable inputs in the same shape as the real data."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from bankstocks.sources import TORONTO


def months(start: str, n: int) -> pd.PeriodIndex:
    return pd.period_range(start, periods=n, freq="M")


def frame(closes: list[float], dividends: list[float] | None = None, start: str = "2020-01") -> pd.DataFrame:
    index = months(start, len(closes))
    dividends = dividends or [0.0] * len(closes)
    return pd.DataFrame({"close": closes, "adjclose": closes, "dividend": dividends}, index=index, dtype="float64")


def month_start(period: str) -> int:
    p = pd.Period(period, freq="M")
    return int(datetime(p.year, p.month, 1, tzinfo=TORONTO).timestamp())


def yahoo_payload(
    start: str,
    closes: list[float],
    dividends: dict[str, float] | None = None,
    currency: str = "CAD",
    extra_bar: float | None = None,
) -> dict:
    """A Yahoo chart response with one bar per month, plus an optional repeated last month."""
    periods = [str(p) for p in months(start, len(closes))]
    stamps = [month_start(p) for p in periods]
    closes = list(closes)
    if extra_bar is not None:  # Yahoo sometimes adds a second, intra-month bar for the latest month
        stamps.append(stamps[-1] + 15 * 86_400)
        closes.append(extra_bar)
    events = {
        str(i): {"date": month_start(p) + 10 * 86_400, "amount": amount}
        for i, (p, amount) in enumerate((dividends or {}).items())
    }
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "TEST.TO", "currency": currency},
                    "timestamp": stamps,
                    "indicators": {"quote": [{"close": closes}], "adjclose": [{"adjclose": closes}]},
                    "events": {"dividends": events},
                }
            ],
            "error": None,
        }
    }
