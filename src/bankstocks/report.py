"""Turn prices and the policy rate into findings, tables, charts and a Markdown report.

Every sentence in the findings is built from a calculated number, so re-running the
report on newer data can't leave stale claims behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from . import charts
from . import metrics as m
from .universe import Security

README_START = "<!-- results:start -->"
README_END = "<!-- results:end -->"
ADJCLOSE_TOLERANCE = 0.005  # 0.5 points a year
MIN_CYCLE_CHANGE = 0.5  # percentage points of policy rate


def is_significant(cycle: m.RateCycle) -> bool:
    """A cycle worth reporting: the rate moved at least MIN_CYCLE_CHANGE points in total.

    Counting moves instead would miss March 2020, when three cuts fell in one month.
    """
    return abs(cycle.rate_after - cycle.rate_before) >= MIN_CYCLE_CHANGE - 1e-9


@dataclass
class Row:
    label: str
    name: str
    ticker: str
    returns: pd.Series
    total: float  # annualised total return
    price: float  # annualised price return
    vol: float
    beta: float
    drawdown: m.Drawdown
    trailing_yield: float | None = None
    dividend_growth: float | None = None
    cuts: list = field(default_factory=list)
    adjclose_gap: float | None = None  # Yahoo's adjusted-close return minus ours, per year

    @property
    def from_dividends(self) -> float:
        return self.total - self.price

    @property
    def final_value(self) -> float:
        return float(m.growth_of(self.returns).iloc[-1])


@dataclass
class CycleResult:
    cycle: m.RateCycle
    banks: float
    benchmark: float


@dataclass
class Analysis:
    start: pd.Period  # the month the $10,000 is invested (end of month)
    end: pd.Period
    banks: list[Row]
    equal_weight: Row
    benchmark: Row
    rate: pd.Series
    cycles: list[CycleResult]

    @property
    def months(self) -> int:
        return len(self.benchmark.returns)


def _row(security: Security, frame: pd.DataFrame, market: pd.Series) -> Row:
    returns = m.total_returns(frame)
    adj = frame["adjclose"]
    adj_total = float((adj.iloc[-1] / adj.iloc[0]) ** (12 / (len(adj) - 1)) - 1)
    return Row(
        label=security.short,
        name=security.name,
        ticker=security.ticker,
        returns=returns,
        total=m.annualised(returns),
        price=m.annualised(m.price_returns(frame)),
        vol=m.volatility(returns),
        beta=m.beta(returns, market),
        drawdown=m.max_drawdown(m.growth_of(returns)),
        trailing_yield=m.trailing_yield(frame),
        dividend_growth=m.dividend_growth(frame),
        cuts=m.dividend_cuts(frame),
        adjclose_gap=adj_total - m.annualised(returns),
    )


def analyse(banks: dict[Security, pd.DataFrame], benchmark: tuple[Security, pd.DataFrame], rate: pd.Series) -> Analysis:
    bench_security, bench_frame = benchmark
    market = m.total_returns(bench_frame)
    rows = [_row(s, f, market) for s, f in banks.items()]
    bench = _row(bench_security, bench_frame, market)

    # Equal weight: the average of the six monthly returns, i.e. rebalanced every month.
    ew_returns = pd.concat([r.returns for r in rows], axis=1).mean(axis=1)
    ew_price = pd.concat([m.price_returns(f) for f in banks.values()], axis=1).mean(axis=1)
    equal_weight = Row(
        label="Big Six, equal weight",
        name="Equal-weight portfolio of the six banks, rebalanced monthly",
        ticker="",
        returns=ew_returns,
        total=m.annualised(ew_returns),
        price=m.annualised(ew_price),
        vol=m.volatility(ew_returns),
        beta=m.beta(ew_returns, market),
        drawdown=m.max_drawdown(m.growth_of(ew_returns)),
    )

    cycles = [
        CycleResult(
            c,
            m.return_over(ew_returns, c.first_move, c.last_move),
            m.return_over(market, c.first_move, c.last_move),
        )
        for c in m.rate_cycles(rate)
        if is_significant(c) and c.first_move >= market.index[0]
    ]
    return Analysis(bench_frame.index[0], bench_frame.index[-1], rows, equal_weight, bench, rate, cycles)


# ---------------------------------------------------------------- formatting


def pct(x: float | None, digits: int = 1, sign: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x:+.{digits}%}" if sign else f"{x:.{digits}%}"


def month(p: pd.Period | None) -> str:
    return "not yet" if p is None else p.strftime("%b %Y")


def money(x: float) -> str:
    return f"${x:,.0f}"


def _rate(x: float) -> str:
    return f"{x:.2f}%"


def span(first: pd.Period, last: pd.Period, joiner: str = " to ") -> str:
    return month(first) if first == last else f"{month(first)}{joiner}{month(last)}"


# ---------------------------------------------------------------- findings


def findings(a: Analysis) -> list[str]:
    ew, bench = a.equal_weight, a.benchmark
    years = a.months / 12
    period = f"{month(a.start)} to {month(a.end)}"
    out = []

    compare = "more" if ew.total > bench.total else "less"
    out.append(
        f"**$10,000 in the Big Six grew to {money(ew.final_value)}** ({period}, dividends reinvested, "
        f"equal weight). That's {pct(ew.total)} a year, {abs(ew.total - bench.total) * 100:.1f} percentage "
        f"points a year {compare} than the TSX 60 (XIU), which turned $10,000 into {money(bench.final_value)}."
    )

    ranked = sorted(a.banks, key=lambda r: r.total, reverse=True)
    best, worst = ranked[0], ranked[-1]
    out.append(
        f"**{best.label} returned the most and {worst.label} the least**: {pct(best.total)} vs "
        f"{pct(worst.total)} a year. Over {years:.0f} years that gap is the difference between "
        f"{money(best.final_value)} and {money(worst.final_value)}."
    )

    avg_div = sum(r.from_dividends for r in a.banks) / len(a.banks)
    avg_price = sum(r.price for r in a.banks) / len(a.banks)
    share = avg_div / (avg_div + avg_price) if avg_div + avg_price > 0 else None
    lead = "Dividends did much of the work." if share is not None and share >= 0.4 else "Dividends added to returns."
    sentence = (
        f"**{lead}** For the average bank, share prices rose {pct(avg_price)} a year and dividends "
        f"added another {pct(avg_div)}"
    )
    out.append(sentence + (f", about {share:.0%} of the total." if share is not None else "."))

    cutters = [r for r in a.banks if r.cuts]
    if not cutters:
        growth = sorted(a.banks, key=lambda r: r.dividend_growth or 0, reverse=True)
        out.append(
            f"**None of the six cut its dividend per share** at any point in the period. Dividend "
            f"growth ranged from {pct(growth[-1].dividend_growth)} a year ({growth[-1].label}) to "
            f"{pct(growth[0].dividend_growth)} ({growth[0].label})."
        )
    else:
        listed = "; ".join(f"{r.label} in {', '.join(month(c[0]) for c in r.cuts)}" for r in cutters)
        out.append(f"**Dividend cuts** (a payment smaller than the one before): {listed}.")

    d, bd = ew.drawdown, bench.drawdown
    out.append(
        f"**The worst stretch for the group was a {pct(-d.depth, 0)} fall** from {month(d.peak)} to "
        f"{month(d.trough)} (month-end values), recovered by {month(d.recovered)}. The TSX 60's worst "
        f"was {pct(-bd.depth, 0)} ({month(bd.peak)} to {month(bd.trough)})."
    )

    betas = sorted(a.banks, key=lambda r: r.beta)
    if ew.beta > 1.2:
        moved = "more than the market"
    elif ew.beta < 0.8:
        moved = "less than the market"
    else:
        moved = "roughly in line with the market"
    out.append(
        f"**Bank shares moved {moved}**: the group's beta against the TSX 60 "
        f"was {ew.beta:.2f}, ranging from {betas[0].beta:.2f} ({betas[0].label}) to "
        f"{betas[-1].beta:.2f} ({betas[-1].label}). Volatility was {pct(ew.vol, 0)} a year for the "
        f"group vs {pct(bench.vol, 0)} for the TSX 60."
    )

    for c in a.cycles:
        verb = "raised" if c.cycle.direction == "hiking" else "cut"
        lead = "beat" if c.banks > c.benchmark else "trailed"
        out.append(
            f"**While the Bank of Canada {verb} rates from {_rate(c.cycle.rate_before)} to "
            f"{_rate(c.cycle.rate_after)}** ({span(c.cycle.first_move, c.cycle.last_move)}), "
            f"the Big Six returned {pct(c.banks, sign=True)} and {lead} the TSX 60 "
            f"({pct(c.benchmark, sign=True)})."
        )
    return out


# ---------------------------------------------------------------- tables


def returns_table(a: Analysis) -> str:
    head = (
        "| | Total return / yr | From price | From dividends | $10,000 became | Volatility | "
        "Beta | Worst fall | Back to peak |\n|---|---|---|---|---|---|---|---|---|\n"
    )
    lines = []
    for r in sorted(a.banks, key=lambda r: r.total, reverse=True) + [a.equal_weight, a.benchmark]:
        bold = "**" if r is a.equal_weight or r is a.benchmark else ""
        d = r.drawdown
        lines.append(
            f"| {bold}{r.label}{bold} | {pct(r.total)} | {pct(r.price)} | {pct(r.from_dividends)} | "
            f"{money(r.final_value)} | {pct(r.vol, 0)} | {r.beta:.2f} | "
            f"{pct(d.depth, 0)} ({month(d.peak)} → {month(d.trough)}) | {month(d.recovered)} |"
        )
    return head + "\n".join(lines)


def dividend_table(a: Analysis) -> str:
    head = "| | Yield (last 12 months) | Dividend growth / yr | Cuts |\n|---|---|---|---|\n"
    lines = [
        f"| {r.label} | {pct(r.trailing_yield)} | {pct(r.dividend_growth)} | "
        f"{', '.join(month(c[0]) for c in r.cuts) or 'none'} |"
        for r in sorted(a.banks, key=lambda r: r.trailing_yield or 0, reverse=True)
    ]
    return head + "\n".join(lines)


def cycles_table(a: Analysis) -> str:
    if not a.cycles:
        return f"_No rate cycle of {MIN_CYCLE_CHANGE} points or more in this period._"
    head = "| Cycle | Policy rate | Months | Big Six | TSX 60 |\n|---|---|---|---|---|\n"
    lines = [
        f"| {c.cycle.direction.capitalize()}, {span(c.cycle.first_move, c.cycle.last_move, ' – ')} | "
        f"{_rate(c.cycle.rate_before)} → {_rate(c.cycle.rate_after)} | "
        f"{(c.cycle.last_move - c.cycle.first_move).n + 1} | {pct(c.banks, sign=True)} | "
        f"{pct(c.benchmark, sign=True)} |"
        for c in a.cycles
    ]
    return head + "\n".join(lines)


def check_table(a: Analysis) -> str:
    head = "| | Our total return / yr | Yahoo adjusted close / yr | Gap |\n|---|---|---|---|\n"
    lines = []
    for r in a.banks + [a.benchmark]:
        flag = "" if abs(r.adjclose_gap) <= ADJCLOSE_TOLERANCE else " ⚠"
        lines.append(
            f"| {r.label} | {pct(r.total, 2)} | {pct(r.total + r.adjclose_gap, 2)} | "
            f"{r.adjclose_gap * 100:+.2f} pts{flag} |"
        )
    return head + "\n".join(lines)


# ---------------------------------------------------------------- output


def draw_charts(a: Analysis, chart_dir: Path) -> dict[str, Path]:
    source = (
        f"Data: Yahoo Finance (prices, dividends), Bank of Canada (policy rate). "
        f"Monthly, {month(a.start)} – {month(a.end)}."
    )
    bench = (a.benchmark.label, m.growth_of(a.benchmark.returns))
    return {
        "growth": charts.growth_chart(
            {r.label: m.growth_of(r.returns) for r in a.banks}, bench, chart_dir / "growth.png", source
        ),
        "breakdown": charts.return_breakdown_chart(
            [(r.label, r.price, r.from_dividends) for r in sorted(a.banks, key=lambda r: r.total, reverse=True)]
            + [(a.benchmark.label, a.benchmark.price, a.benchmark.from_dividends)],
            chart_dir / "breakdown.png",
            source,
        ),
        "drawdowns": charts.drawdown_chart(
            m.growth_of(a.equal_weight.returns), bench, chart_dir / "drawdowns.png", source
        ),
        "rates": charts.rate_chart(
            a.rate.loc[a.start :], m.growth_of(a.equal_weight.returns), bench, chart_dir / "rates.png", source
        ),
    }


def render(a: Analysis, generated: date) -> str:
    bullets = "\n".join(f"- {f}" for f in findings(a))
    return f"""# Canada's Big Six banks: {a.months // 12} years of shareholder returns

{month(a.start)} to {month(a.end)} ({a.months} monthly returns), in Canadian dollars. Generated
{generated:%b %-d, %Y} by `python -m bankstocks`. **This is historical analysis, not investment
advice.** Past returns don't predict future ones.

## Key findings

{bullets}

## Growth of $10,000

![Growth of $10,000 in each bank and the TSX 60](charts/growth.png)

## Returns and risk

{returns_table(a)}

- **Total return** includes dividends, reinvested at the month-end close. **From price** and
  **from dividends** split it into share-price growth and the extra return from dividends.
- **Volatility** is the annualised standard deviation of monthly returns.
- **Beta** measures how much a stock moved, on average, for each 1% move in the TSX 60.
- **Worst fall** and **back to peak** use month-end values, so falls within a month look smaller.

![Price growth and dividends per year](charts/breakdown.png)

![Fall from previous high](charts/drawdowns.png)

## Dividends

{dividend_table(a)}

Dividend growth compares the first and last payment per share in the period. A **cut** is any
payment smaller than the one before it.

## Interest-rate cycles

Cycles are found from the data: consecutive policy-rate moves in the same direction that add
up to at least {MIN_CYCLE_CHANGE} percentage points. Returns run from the end of the month before
the first move to the end of the month of the last one.

{cycles_table(a)}

![Policy rate and bank returns](charts/rates.png)

## Data check

As a cross-check, our compounded total return is compared with the return implied by Yahoo's own
dividend-adjusted close. Small gaps are expected: Yahoo reinvests dividends on the ex-date, this
analysis at the month end. Gaps over {ADJCLOSE_TOLERANCE * 100:.1f} points a year are flagged ⚠.

{check_table(a)}

## Method and limitations

- **Survivorship:** these are the six largest banks *today*. Picking today's winners and looking
  back flatters past returns.
- **Monthly data:** returns, volatility and falls are measured month end to month end.
- **No taxes, fees or trading costs** for the banks. XIU's returns are after its management fee.
- **Dividends** are counted in the month of their ex-dividend date and reinvested at that
  month's close.
- **Equal weight** means the six banks are held in equal amounts, rebalanced every month.
- **Data:** prices and dividends from Yahoo Finance's public chart data, which is unofficial and
  can contain errors (see the data check). Policy rate from the Bank of Canada's Valet API,
  series V39079, taken at month end.
"""


def readme_section(a: Analysis) -> str:
    bullets = "\n".join(f"- {f}" for f in findings(a)[:4])
    return f"""{README_START}
_{month(a.start)} to {month(a.end)}, dividends reinvested. Full report: [report/REPORT.md](report/REPORT.md)._

{bullets}

![Growth of $10,000 in each bank and the TSX 60](report/charts/growth.png)
{README_END}"""


def update_readme(path: Path, section: str) -> bool:
    """Replace the results section between the markers. Returns False if the markers are missing."""
    text = path.read_text()
    start, end = text.find(README_START), text.find(README_END)
    if start == -1 or end == -1:
        return False
    path.write_text(text[:start] + section + text[end + len(README_END) :])
    return True


def write_report(a: Analysis, out_dir: Path, generated: date) -> Path:
    draw_charts(a, out_dir / "charts")
    path = out_dir / "REPORT.md"
    path.write_text(render(a, generated))
    return path
