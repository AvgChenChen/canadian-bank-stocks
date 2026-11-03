# Walkthrough: how this project works, in plain language

Read this before you talk about the project. It explains what each piece does and why, and
ends with questions you might be asked.

## The question

"If I'd put $10,000 into Canada's big banks ten years ago, what would I have now, and was it
worth it compared with just buying the whole market?" Bank stocks are popular with Canadian
investors because of their dividends, so the project also asks how much of the return came from
dividends and how the banks behaved when interest rates moved.

## The pipeline, step by step

1. **Get the data** ([`sources.py`](../src/bankstocks/sources.py)). For each bank and for XIU, it
   downloads ten years of month-end prices and every dividend payment. From the Bank of Canada, it
   downloads the policy rate. Downloads are saved in `data/raw/`, so a second run is instant and
   doesn't depend on the internet.
2. **Check the data.** If a month is missing, a price is in US dollars, or the website returns an
   error, the run stops with a clear message. A gap you don't notice is worse than a crash.
3. **Calculate** ([`metrics.py`](../src/bankstocks/metrics.py)). Each month's return is
   `(this month's price + dividends paid) / last month's price - 1`. Everything else is built from
   that one series of monthly returns.
4. **Write it up** ([`report.py`](../src/bankstocks/report.py), [`charts.py`](../src/bankstocks/charts.py)).
   The findings are sentences filled in by code. "National Bank returned the most" is only written
   because the code sorted the banks and National Bank came first. If the data changes, the
   sentence changes.

## The measures, and what they mean for an investor

| Measure | Plain meaning | How it's calculated |
|---|---|---|
| Total return per year | How fast the money grew, including dividends | Multiply all the `(1 + monthly return)` together, then take the 12/months power and subtract 1 |
| From dividends | How much of that growth came from dividends | Total return minus the return from price alone |
| Volatility | How bumpy the ride was | Standard deviation of monthly returns, times √12 to make it yearly |
| Beta | How much it moved when the market moved | Covariance with XIU's returns divided by XIU's variance. 1.2 means "moved 1.2% for each 1% market move" |
| Worst fall | The most painful drop an investor sat through | The largest fall from a previous high |
| Dividend growth | How fast the payout per share grew | First payment vs last payment, as a yearly rate |
| Rate cycles | How banks did while rates rose or fell | Found automatically from the policy-rate data, then the return over each cycle |

## Design choices worth mentioning

- **Equal weight.** The "Big Six" line holds the same amount in each bank, rebalanced monthly. The
  alternative, weighting by size, would mostly track RBC and TD.
- **XIU as the benchmark.** It's a real ETF an investor could have bought instead, so the
  comparison is fair: "the banks beat what you'd realistically have done otherwise."
- **Cross-checking.** The total return is calculated by hand from prices and dividends, then
  compared with Yahoo's own dividend-adjusted price. The gaps were under 0.1 percentage points a
  year, which is good evidence the calculation is right.
- **Cuts measured by payment, not by year.** If a December dividend slips into January, one year
  shows three payments and the next shows five. Comparing year totals would invent a "cut" that
  never happened.
- **Rate cycles measured by size.** An earlier version needed at least two rate moves and missed
  March 2020, when the Bank of Canada cut three times in one month. Now a cycle counts if the
  rate moved at least 0.5 percentage points in total.

## The limitations, and why they matter

- **Survivorship bias** is the big one. These are the six largest banks *today*. Choosing today's
  winners and looking back makes the past look better than an investor in 2016 could have known.
- **Monthly data** hides falls within a month. The real March 2020 low was deeper than the
  month-end numbers show.
- **No taxes or trading costs.** Real returns would be lower, especially outside a TFSA or RRSP.

## Questions you might be asked

- **"Why did the banks beat the market?"** The data shows higher price growth *and* higher
  dividends than XIU. It doesn't show why. Reasons you could look into: lending margins, loan
  losses, and how concentrated Canadian banking is. Say clearly that these are your
  reasoning and not something the analysis proves.
- **"Banks did badly while rates rose in 2022–23. Doesn't higher rates mean more profit?"** Higher
  rates can widen lending margins, but they also raise loan losses and can slow mortgage growth.
  In this cycle the Big Six fell 9.2% while XIU rose 1.4%, so
  investors seem to have weighed the risks more heavily.
- **"How do you know the numbers are right?"** The cross-check against Yahoo's adjusted prices,
  plus tests that check each formula on small examples where the answer can be worked by hand.
- **"What would you add next?"** Weighting by market size, comparing with US banks, or measuring
  returns after tax in a non-registered account.
