"""What is analysed: the six largest Canadian banks, a market benchmark, and the policy rate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Security:
    ticker: str  # Yahoo Finance symbol on the Toronto Stock Exchange
    name: str
    short: str  # label used in tables and charts


BANKS = [
    Security("RY.TO", "Royal Bank of Canada", "RBC"),
    Security("TD.TO", "Toronto-Dominion Bank", "TD"),
    Security("BNS.TO", "Bank of Nova Scotia", "Scotiabank"),
    Security("BMO.TO", "Bank of Montreal", "BMO"),
    Security("CM.TO", "Canadian Imperial Bank of Commerce", "CIBC"),
    Security("NA.TO", "National Bank of Canada", "National Bank"),
]

# An ETF that tracks the S&P/TSX 60, so it's something an investor could actually have bought
# instead. Its returns are after its management fee; the banks' are not reduced by any fee.
BENCHMARK = Security("XIU.TO", "iShares S&P/TSX 60 Index ETF", "TSX 60 (XIU)")

# Bank of Canada Valet series: target for the overnight rate (the policy rate).
POLICY_RATE_SERIES = "V39079"
