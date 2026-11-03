import json

import pandas as pd
import pytest

from bankstocks import sources
from bankstocks.sources import DataError, load_prices, parse_valet_monthly, parse_yahoo_monthly

from .helpers import yahoo_payload

JAN, APR = pd.Period("2020-01", "M"), pd.Period("2020-04", "M")


def test_parses_closes_and_puts_dividends_in_their_ex_date_month():
    payload = yahoo_payload("2020-01", [10, 11, 12, 13, 14], dividends={"2020-02": 0.5, "2020-04": 0.25})
    f = parse_yahoo_monthly(payload, JAN, APR)
    assert list(f.index.astype(str)) == ["2020-01", "2020-02", "2020-03", "2020-04"]  # May is after the end
    assert f["close"].tolist() == [10, 11, 12, 13]
    assert f["dividend"].tolist() == [0, 0.5, 0, 0.25]


def test_a_repeated_bar_for_the_latest_month_keeps_the_later_one():
    payload = yahoo_payload("2020-01", [10, 11, 12, 13], extra_bar=13.5)
    assert parse_yahoo_monthly(payload, JAN, APR)["close"].iloc[-1] == 13.5


def test_a_missing_month_is_an_error_not_a_silent_gap():
    payload = yahoo_payload("2020-01", [10, 11, None, 13])
    with pytest.raises(DataError, match="2020-03"):
        parse_yahoo_monthly(payload, JAN, APR)


def test_a_range_the_data_does_not_cover_is_an_error():
    with pytest.raises(DataError, match="2020-04"):
        parse_yahoo_monthly(yahoo_payload("2020-01", [10, 11, 12]), JAN, APR)


def test_prices_in_another_currency_are_rejected():
    with pytest.raises(DataError, match="USD"):
        parse_yahoo_monthly(yahoo_payload("2020-01", [10, 11, 12, 13], currency="USD"), JAN, APR)


def test_an_error_response_is_reported():
    with pytest.raises(DataError, match="Not Found"):
        parse_yahoo_monthly({"chart": {"result": None, "error": {"code": "Not Found"}}}, JAN, APR)


def test_valet_takes_the_last_observation_of_each_month():
    payload = {
        "observations": [
            {"d": "2020-01-15", "V1": {"v": "1.75"}},
            {"d": "2020-01-31", "V1": {"v": "1.75"}},
            {"d": "2020-02-03", "V1": {"v": "1.75"}},
            {"d": "2020-02-28", "V1": {"v": "1.25"}},
        ]
    }
    rate = parse_valet_monthly(payload, "V1", JAN, pd.Period("2020-02", "M"))
    assert rate.tolist() == [1.75, 1.25]


def test_cached_data_is_used_without_downloading(tmp_path, monkeypatch):
    payload = yahoo_payload("2020-01", [10, 11, 12, 13])
    (tmp_path / "TEST.TO_2020-01_2020-04.json").write_text(json.dumps(payload))

    def no_network(*_):
        raise AssertionError("should have used the cache")

    monkeypatch.setattr(sources, "_get_json", no_network)
    assert load_prices("TEST.TO", JAN, APR, tmp_path)["close"].tolist() == [10, 11, 12, 13]


def test_refresh_downloads_and_rewrites_the_cache(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, params):
        calls.append((url, params))
        return yahoo_payload("2020-01", [10, 11, 12, 13])

    monkeypatch.setattr(sources, "_get_json", fake_get)
    load_prices("TEST.TO", JAN, APR, tmp_path, refresh=True)
    assert len(calls) == 1
    assert calls[0][1]["interval"] == "1mo" and calls[0][1]["events"] == "div"
    assert (tmp_path / "TEST.TO_2020-01_2020-04.json").exists()
