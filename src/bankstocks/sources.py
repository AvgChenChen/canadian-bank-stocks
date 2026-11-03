"""Download, cache and parse the raw data.

- Prices and dividends: Yahoo Finance's public chart endpoint. It is unofficial and needs no key.
- Policy rate: the Bank of Canada Valet API, which is official and needs no key.

Raw responses are cached under data/raw/ and are not committed to the repository.
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import certifi
import pandas as pd

TORONTO = ZoneInfo("America/Toronto")
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
VALET_URL = "https://www.bankofcanada.ca/valet/observations/{series}/json"


class DataError(Exception):
    """The downloaded data is missing something the analysis needs."""


def _month(timestamp: int) -> pd.Period:
    # Yahoo stamps each monthly bar at midnight Toronto time on the 1st of the month.
    return pd.Period(datetime.fromtimestamp(timestamp, TORONTO).strftime("%Y-%m"), freq="M")


def parse_yahoo_monthly(payload: dict, start: pd.Period, end: pd.Period) -> pd.DataFrame:
    """Turn a Yahoo monthly chart response into one row per month from start to end.

    Columns: close (last close of the month), adjclose (Yahoo's dividend-adjusted close,
    kept only to cross-check our own calculation) and dividend (total paid per share,
    by ex-dividend month).
    """
    try:
        result = payload["chart"]["result"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise DataError(f"Unexpected Yahoo response: {payload.get('chart', {}).get('error')}") from exc

    symbol = result["meta"].get("symbol", "?")
    currency = result["meta"].get("currency")
    if currency != "CAD":
        raise DataError(f"{symbol} is priced in {currency}, expected CAD")

    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame(
        {"close": quote["close"], "adjclose": result["indicators"]["adjclose"][0]["adjclose"]},
        index=pd.PeriodIndex([_month(ts) for ts in result["timestamp"]], freq="M"),
        dtype="float64",
    )
    # Yahoo sometimes repeats the current month as a second bar; keep the latest.
    frame = frame[~frame.index.duplicated(keep="last")].loc[start:end]

    expected = pd.period_range(start, end, freq="M")
    missing = expected.difference(frame.dropna().index)
    if len(missing):
        raise DataError(f"{symbol} has no price for {', '.join(str(m) for m in missing[:5])}")

    dividend = pd.Series(0.0, index=frame.index)
    for event in result.get("events", {}).get("dividends", {}).values():
        month = _month(event["date"])
        if month in dividend.index:
            dividend[month] += float(event["amount"])
    frame["dividend"] = dividend
    return frame


def parse_valet_monthly(payload: dict, series: str, start: pd.Period, end: pd.Period) -> pd.Series:
    """Month-end value of a Bank of Canada series (the last observation in each month)."""
    rows = [(o["d"], o[series]["v"]) for o in payload.get("observations", []) if series in o]
    if not rows:
        raise DataError(f"No observations for Bank of Canada series {series}")
    daily = pd.Series([float(v) for _, v in rows], index=pd.to_datetime([d for d, _ in rows]), name=series).sort_index()
    monthly = daily.groupby(daily.index.to_period("M")).last().loc[start:end]
    missing = pd.period_range(start, end, freq="M").difference(monthly.index)
    if len(missing):
        raise DataError(f"Series {series} has no value for {', '.join(str(m) for m in missing[:5])}")
    return monthly


def _get_json(url: str, params: dict) -> dict:
    request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "Mozilla/5.0"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return json.load(response)


def _cached(path: Path, fetch, refresh: bool) -> dict:
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    payload = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return payload


def load_prices(ticker: str, start: pd.Period, end: pd.Period, cache_dir: Path, refresh: bool = False) -> pd.DataFrame:
    first = datetime(start.year, start.month, 1, tzinfo=TORONTO)
    after = (end + 1).start_time.tz_localize(TORONTO)
    params = {
        "period1": int(first.timestamp()),
        "period2": int(after.timestamp()),
        "interval": "1mo",
        "events": "div",
        "includeAdjustedClose": "true",
    }
    path = cache_dir / f"{ticker}_{start}_{end}.json"
    payload = _cached(path, lambda: _get_json(YAHOO_URL.format(ticker=ticker), params), refresh)
    return parse_yahoo_monthly(payload, start, end)


def load_policy_rate(
    series: str, start: pd.Period, end: pd.Period, cache_dir: Path, refresh: bool = False
) -> pd.Series:
    params = {"start_date": start.start_time.date().isoformat(), "end_date": end.end_time.date().isoformat()}
    path = cache_dir / f"{series}_{start}_{end}.json"
    payload = _cached(path, lambda: _get_json(VALET_URL.format(series=series), params), refresh)
    return parse_valet_monthly(payload, series, start, end)
