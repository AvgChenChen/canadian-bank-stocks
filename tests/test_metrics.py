import math

import pandas as pd
import pytest

from bankstocks import metrics as m

from .helpers import frame, months


def test_total_return_adds_dividends_to_the_price_change():
    f = frame([100, 110, 99], dividends=[0, 2, 0])
    returns = m.total_returns(f)
    # Feb: (110 + 2) / 100 - 1 = 12%. Mar: 99 / 110 - 1 = -10%.
    assert list(returns.index.astype(str)) == ["2020-02", "2020-03"]
    assert returns.tolist() == pytest.approx([0.12, -0.10])
    assert m.price_returns(f).tolist() == pytest.approx([0.10, -0.10])


def test_growth_of_starts_at_the_amount_in_the_month_before_the_first_return():
    returns = pd.Series([0.10, -0.10], index=months("2020-02", 2))
    growth = m.growth_of(returns)
    assert str(growth.index[0]) == "2020-01"
    assert growth.tolist() == pytest.approx([10_000, 11_000, 9_900])


def test_annualised_compounds_monthly_returns():
    returns = pd.Series([0.01] * 24, index=months("2020-01", 24))
    assert m.annualised(returns) == pytest.approx(1.01**12 - 1)
    assert m.compounded(returns) == pytest.approx(1.01**24 - 1)


def test_volatility_annualises_the_monthly_standard_deviation():
    returns = pd.Series([0.02, -0.02] * 6, index=months("2020-01", 12))
    assert m.volatility(returns) == pytest.approx(returns.std(ddof=1) * math.sqrt(12))


def test_beta_of_a_stock_that_moves_twice_as_much_as_the_market_is_two():
    market = pd.Series([0.01, -0.02, 0.03, 0.00, -0.01], index=months("2020-01", 5))
    assert m.beta(market * 2, market) == pytest.approx(2.0)
    assert m.beta(market, market) == pytest.approx(1.0)


def test_max_drawdown_finds_peak_trough_and_recovery():
    values = pd.Series([100, 120, 90, 60, 130, 125], index=months("2020-01", 6), dtype="float64")
    d = m.max_drawdown(values)
    assert d.depth == pytest.approx(-0.5)  # 120 -> 60
    assert (str(d.peak), str(d.trough), str(d.recovered)) == ("2020-02", "2020-04", "2020-05")


def test_max_drawdown_without_recovery():
    values = pd.Series([100, 80, 90], index=months("2020-01", 3), dtype="float64")
    d = m.max_drawdown(values)
    assert d.depth == pytest.approx(-0.2)
    assert d.recovered is None


def test_trailing_yield_uses_the_last_twelve_months_of_dividends():
    dividends = [5.0] + [0.0] * 3 + [1.0, 0, 0] * 4  # 16 months; the 5.0 is too old to count
    f = frame([100.0] * 15 + [80.0], dividends=dividends)
    assert m.trailing_yield(f) == pytest.approx(4.0 / 80.0)


def test_dividend_growth_compares_first_and_last_payment():
    dividends = [0.0] * 25
    dividends[0], dividends[12], dividends[24] = 1.0, 1.1, 1.21
    f = frame([100.0] * 25, dividends=dividends)
    assert m.dividend_growth(f) == pytest.approx(0.10)


def test_dividend_growth_needs_two_payments():
    assert m.dividend_growth(frame([100.0] * 3, dividends=[0, 1, 0])) is None


def test_a_smaller_payment_is_a_cut():
    f = frame([100.0] * 6, dividends=[1.0, 0, 1.0, 0, 0.5, 0.6])
    cuts = m.dividend_cuts(f)
    assert [(str(p), before, now) for p, before, now in cuts] == [("2020-05", 1.0, 0.5)]


def test_an_ex_date_moving_into_the_next_year_is_not_a_cut():
    # Payments in Oct and the following Jan instead of Dec: a calendar-year total would dip.
    dividends = [0.0] * 13
    dividends[0], dividends[3], dividends[6], dividends[9], dividends[12] = 1, 1, 1, 1, 1.05
    assert m.dividend_cuts(frame([100.0] * 13, dividends=dividends, start="2020-01")) == []


def test_rate_cycles_group_moves_in_the_same_direction():
    rate = pd.Series([0.25, 0.25, 0.50, 1.00, 1.00, 1.50, 1.00, 0.75], index=months("2022-01", 8))
    cycles = m.rate_cycles(rate)
    assert [
        (c.direction, str(c.first_move), str(c.last_move), c.rate_before, c.rate_after, c.moves) for c in cycles
    ] == [
        ("hiking", "2022-03", "2022-06", 0.25, 1.50, 3),
        ("cutting", "2022-07", "2022-08", 1.50, 0.75, 2),
    ]


def test_return_over_compounds_the_months_in_the_window():
    returns = pd.Series([0.5, 0.10, 0.10, 0.5], index=months("2022-01", 4))
    assert m.return_over(returns, pd.Period("2022-02", "M"), pd.Period("2022-03", "M")) == pytest.approx(0.21)


@pytest.mark.parametrize("calculate", [m.growth_of, m.annualised, m.compounded])
def test_empty_monthly_returns_raise_a_clear_error(calculate):
    empty = pd.Series(dtype="float64", index=months("2020-01", 0))
    with pytest.raises(ValueError, match="At least one monthly return is required"):
        calculate(empty)
