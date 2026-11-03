"""Charts for the report. Each function writes one PNG and returns its path."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files, no window

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

# Okabe-Ito colours: distinguishable with the common forms of colour blindness.
COLOURS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]
BENCHMARK_STYLE = {"color": "#222222", "linestyle": "--", "linewidth": 2}
BANKS_STYLE = {"color": "#0072B2", "linewidth": 2}


def _style(ax, title: str) -> None:
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#dddddd", linewidth=0.8)
    ax.set_axisbelow(True)


def _x(index: pd.PeriodIndex):
    return index.to_timestamp(how="end")


def _save(fig, path: Path, source: str) -> Path:
    fig.text(0.01, 0.01, source, fontsize=8, color="#666666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def growth_chart(growth: dict[str, pd.Series], benchmark: tuple[str, pd.Series], path: Path, source: str) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for (label, series), colour in zip(growth.items(), COLOURS, strict=False):
        ax.plot(_x(series.index), series.values, label=label, color=colour, linewidth=1.8)
    name, series = benchmark
    ax.plot(_x(series.index), series.values, label=name, **BENCHMARK_STYLE)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    _style(ax, "Growth of $10,000 with dividends reinvested (CAD)")
    ax.legend(frameon=False, ncol=4, loc="upper left", fontsize=9)
    return _save(fig, path, source)


def return_breakdown_chart(rows: list[tuple[str, float, float]], path: Path, source: str) -> Path:
    """rows: (label, price return per year, dividend contribution per year)."""
    labels = [r[0] for r in rows]
    price = [r[1] for r in rows]
    dividend = [r[2] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, price, color="#0072B2", label="Share price growth")
    ax.bar(labels, dividend, bottom=price, color="#E69F00", label="Dividends")
    for i, (p, d) in enumerate(zip(price, dividend, strict=True)):
        ax.text(i, p + d + 0.002, f"{p + d:.1%}", ha="center", fontsize=9)
    ax.axhline(0, color="#999999", linewidth=0.8)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    _style(ax, "Where the yearly return came from")
    ax.legend(frameon=False, loc="upper right")
    return _save(fig, path, source)


def drawdown_chart(banks: pd.Series, benchmark: tuple[str, pd.Series], path: Path, source: str) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for label, series, style in [("Big Six, equal weight", banks, BANKS_STYLE), (*benchmark, BENCHMARK_STYLE)]:
        from_high = series / series.cummax() - 1
        ax.plot(_x(from_high.index), from_high.values, label=label, **style)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    _style(ax, "Fall from previous high (month-end values)")
    ax.legend(frameon=False, loc="lower left")
    return _save(fig, path, source)


def rate_chart(rate: pd.Series, banks: pd.Series, benchmark: tuple[str, pd.Series], path: Path, source: str) -> Path:
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, height_ratios=(1, 1.4))
    top.step(_x(rate.index), rate.values, where="post", color="#D55E00", linewidth=2)
    top.yaxis.set_major_formatter(PercentFormatter(100.0, decimals=1))
    _style(top, "Bank of Canada policy rate")
    bottom.plot(_x(banks.index), banks.values, label="Big Six, equal weight", **BANKS_STYLE)
    name, series = benchmark
    bottom.plot(_x(series.index), series.values, label=name, **BENCHMARK_STYLE)
    bottom.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    _style(bottom, "Growth of $10,000 (CAD)")
    bottom.legend(frameon=False, loc="upper left")
    return _save(fig, path, source)
