"""Return, risk and dividend measures. Every function works on monthly data.

Conventions:
- A monthly total return is (this month's close + dividends with an ex-date this month)
  / last month's close - 1. Dividends are assumed reinvested at the month-end close.
- Annualised numbers compound monthly returns: (product of (1 + r)) ^ (12 / months) - 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


def total_returns(frame: pd.DataFrame) -> pd.Series:
    """Monthly total returns. The first month is the starting point, so it has no return."""
    return ((frame["close"] + frame["dividend"]) / frame["close"].shift(1) - 1).iloc[1:]


def price_returns(frame: pd.DataFrame) -> pd.Series:
    return frame["close"].pct_change().iloc[1:]


def _require_returns(returns: pd.Series) -> None:
    if returns.empty:
        raise ValueError("At least one monthly return is required")


def growth_of(returns: pd.Series, amount: float = 10_000.0) -> pd.Series:
    """Value of `amount` invested at the end of the month before the first return."""
    _require_returns(returns)
    index = (1 + returns).cumprod() * amount
    start = pd.Series([amount], index=pd.PeriodIndex([returns.index[0] - 1], freq="M"))
    return pd.concat([start, index])


def annualised(returns: pd.Series) -> float:
    _require_returns(returns)
    return float((1 + returns).prod() ** (12 / len(returns)) - 1)


def compounded(returns: pd.Series) -> float:
    _require_returns(returns)
    return float((1 + returns).prod() - 1)


def volatility(returns: pd.Series) -> float:
    """Annualised standard deviation of monthly returns."""
    return float(returns.std(ddof=1) * math.sqrt(12))


def beta(returns: pd.Series, market: pd.Series) -> float:
    """How much the stock moved, on average, for each 1% move in the market."""
    return float(returns.cov(market) / market.var())


@dataclass(frozen=True)
class Drawdown:
    depth: float  # e.g. -0.35 for a 35% fall from the previous high
    peak: pd.Period
    trough: pd.Period
    recovered: pd.Period | None  # first month back at or above the peak; None if not yet


def max_drawdown(values: pd.Series) -> Drawdown:
    """Largest fall from a previous high, measured on month-end values."""
    from_high = values / values.cummax() - 1
    trough = from_high.idxmin()
    peak = values.loc[:trough].idxmax()
    later = values.loc[trough:]
    back = later[later >= values[peak]]
    recovered = back.index[0] if len(back) and trough != peak else None
    return Drawdown(float(from_high[trough]), peak, trough, recovered)


def trailing_yield(frame: pd.DataFrame) -> float:
    """Dividends with an ex-date in the last 12 months, divided by the latest close."""
    return float(frame["dividend"].iloc[-12:].sum() / frame["close"].iloc[-1])


def payments(frame: pd.DataFrame) -> pd.Series:
    """Dividend per share in each month that had an ex-dividend date."""
    return frame["dividend"][frame["dividend"] > 0]


def dividend_growth(frame: pd.DataFrame) -> float | None:
    """Annualised growth from the first payment in the window to the last one.

    Comparing single payments, not calendar-year totals, avoids a false "cut" when an
    ex-date moves from late December into January.
    """
    paid = payments(frame)
    if len(paid) < 2:
        return None
    months = (paid.index[-1] - paid.index[0]).n
    return float((paid.iloc[-1] / paid.iloc[0]) ** (12 / months) - 1)


def dividend_cuts(frame: pd.DataFrame) -> list[tuple[pd.Period, float, float]]:
    """Every payment smaller than the one before it: (month, previous amount, new amount)."""
    paid = payments(frame)
    return [
        (month, float(before), float(now))
        for (month, now), before in zip(paid.iloc[1:].items(), paid.iloc[:-1], strict=True)
        if now < before - 1e-9
    ]


@dataclass(frozen=True)
class RateCycle:
    direction: str  # "hiking" or "cutting"
    first_move: pd.Period
    last_move: pd.Period
    rate_before: float
    rate_after: float
    moves: int  # months in which the rate changed


def rate_cycles(rate: pd.Series) -> list[RateCycle]:
    """Group consecutive rate changes in the same direction into cycles.

    Months with no change don't end a cycle; only a move in the other direction does.
    """
    changes = rate.diff().dropna()
    changes = changes[changes.abs() > 1e-9]
    cycles: list[RateCycle] = []
    for month, delta in changes.items():
        direction = "hiking" if delta > 0 else "cutting"
        last = cycles[-1] if cycles else None
        if last and last.direction == direction:
            cycles[-1] = RateCycle(
                direction, last.first_move, month, last.rate_before, float(rate[month]), last.moves + 1
            )
        else:
            cycles.append(RateCycle(direction, month, month, float(rate[month - 1]), float(rate[month]), 1))
    return cycles


def return_over(returns: pd.Series, first: pd.Period, last: pd.Period) -> float:
    """Compounded return from the end of the month before `first` to the end of `last`."""
    return compounded(returns.loc[first:last])
