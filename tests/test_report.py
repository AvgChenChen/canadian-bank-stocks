import re

import pandas as pd
import pytest

from bankstocks import report
from bankstocks.universe import BANKS, BENCHMARK

from .helpers import frame, months

N = 25  # a starting month plus two years of returns


def steady(growth: float, start: float = 100.0, dividend: float = 0.0) -> pd.DataFrame:
    """A price rising by `growth` each month, paying `dividend` per share every third month."""
    closes = [start * (1 + growth) ** i for i in range(N)]
    dividends = [dividend if i % 3 == 0 and i else 0.0 for i in range(N)]
    return frame(closes, dividends)


@pytest.fixture
def analysis():
    growth = [0.010, 0.008, 0.006, 0.004, 0.002, 0.000]
    banks = {s: steady(g, dividend=1.0) for s, g in zip(BANKS, growth, strict=True)}
    # Market: steady growth with one sharp fall, so it has a drawdown and beta is defined.
    closes = [100 * 1.005**i for i in range(N)]
    closes[10] *= 0.8
    market = (BENCHMARK, frame(closes))
    rate = pd.Series([1.0] * 5 + [1.5, 2.0, 2.5] + [2.5] * 9 + [2.0, 1.5] + [1.5] * 6, index=months("2020-01", N))
    return report.analyse(banks, market, rate)


def test_banks_are_ranked_by_total_return(analysis):
    text = report.findings(analysis)
    assert any("RBC returned the most and National Bank the least" in f for f in text)


def test_no_cut_is_reported_when_payments_never_shrink(analysis):
    assert any("None of the six cut its dividend" in f for f in report.findings(analysis))


def test_rate_cycles_come_from_the_data(analysis):
    cycles = [(c.cycle.direction, str(c.cycle.first_move), str(c.cycle.last_move)) for c in analysis.cycles]
    assert cycles == [("hiking", "2020-06", "2020-08"), ("cutting", "2021-06", "2021-07")]


def test_dividends_split_out_of_total_return(analysis):
    flat = next(r for r in analysis.banks if r.label == "National Bank")
    assert flat.price == pytest.approx(0.0)
    assert flat.from_dividends > 0  # all of its return came from dividends


def test_our_return_matches_the_adjusted_close_when_there_are_no_dividends(analysis):
    assert analysis.benchmark.adjclose_gap == pytest.approx(0.0, abs=1e-12)


def test_report_and_charts_are_written(tmp_path, analysis):
    from datetime import date

    path = report.write_report(analysis, tmp_path, date(2026, 11, 3))
    text = path.read_text()
    assert "## Key findings" in text and "not investment\nadvice" in text
    assert not re.search(r"\bnan\b", text, re.IGNORECASE)
    for name in ["growth", "breakdown", "drawdowns", "rates"]:
        assert (tmp_path / "charts" / f"{name}.png").stat().st_size > 10_000


def test_readme_section_is_replaced_between_markers(tmp_path, analysis):
    readme = tmp_path / "README.md"
    readme.write_text(f"# Title\n\n{report.README_START}\nold\n{report.README_END}\n\n## After\n")
    assert report.update_readme(readme, report.readme_section(analysis))
    text = readme.read_text()
    assert "old" not in text and "## After" in text and text.count(report.README_START) == 1


def test_readme_without_markers_is_left_alone(tmp_path, analysis):
    readme = tmp_path / "README.md"
    readme.write_text("# Title\n")
    assert not report.update_readme(readme, report.readme_section(analysis))
    assert readme.read_text() == "# Title\n"


def test_a_big_move_inside_one_month_is_a_cycle_but_a_small_one_is_not():
    # March 2020: 1.75% -> 0.25% in one month. A single quarter-point hike later doesn't count.
    rate = pd.Series([1.75, 1.75, 0.25, 0.25, 0.50], index=months("2020-01", 5))
    from bankstocks import metrics as m

    cycles = m.rate_cycles(rate)
    assert [report.is_significant(c) for c in cycles] == [True, False]
    assert report.span(cycles[0].first_move, cycles[0].last_move) == "Mar 2020"
