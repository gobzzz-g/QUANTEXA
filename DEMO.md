# Hackathon Demo Script (3-Minutes)

**0:00 - 0:30 | Introduction & Data**
"Welcome to our Quantitative Multi-Asset Intelligence Platform. We're tracking Bitcoin, Gold, and NVIDIA. Our data layer automatically handles calendar differences (365 days vs 252 days) without leaking future data, and cleans anomalies on the fly. Let's look at the Overview Dashboard showing our real-time metrics."

**0:30 - 1:30 | Strategy Lab & Backtesting**
"Let's jump into the Strategy Lab. We'll run a Mean Reversion strategy on NVIDIA. Notice we account for commissions and slippage by default, and we execute on the *next day's open*—meaning zero look-ahead bias. 
Look at the equity curve compared to our Buy-and-Hold benchmark. The verdict engine instantly tells us if the strategy's Sharpe ratio actually justified the risk."

**1:30 - 2:30 | Robustness & Regimes**
"A single backtest is easy to overfit. We built a robustness module that runs a parameter grid search to ensure the strategy holds up across different windows. We also analyze performance across market regimes—like High Volatility or Bear markets—using an expanding median, so there's no data leakage."

**2:30 - 3:00 | Conclusion**
"Everything is accessible via our scalable FastAPI, built with pandas for vectorization. All metrics match industry standards. It's fully dockerized and ready to deploy."

---

## 10 Likely Judge Questions & Answers

**Q1: How do you handle weekends for Bitcoin vs. Equities?**
A: We evaluate assets on their natural calendar. Cross-asset analysis uses an inner join on common trading dates. We never forward-fill equity prices across weekends, as that artificially creates a 365-day calendar for a 252-day asset.

**Q2: How do you prevent look-ahead bias?**
A: Signals are generated using only information available up to the close of day $t$. The actual trade simulation executes at the open price of day $t+1$.

**Q3: Does your backtest include transaction costs?**
A: Yes. Every trade applies a default 0.1% commission and 5 bps of slippage.

**Q4: How do you calculate the risk-free rate in the Sharpe Ratio?**
A: The risk-free rate is a user-configurable parameter in the UI (default 0%). It is de-annualized inside the backend to compute excess daily returns.

**Q5: What happens if the yfinance API goes down during the demo?**
A: The platform automatically falls back to our pre-downloaded seed CSVs in the `data/seed` directory, so the demo will never break.

**Q6: Are your market regime labels using future data?**
A: No. We use an expanding median for volatility, meaning day $t$'s regime is defined only using data from day $0$ to day $t$. 

**Q7: How did you verify your drawdown calculation?**
A: We wrote unit tests enforcing specific mathematical identities, like ensuring a price path of `[100, 130, 90, 150]` strictly results in a max drawdown of `-30.769%`.

**Q8: Can you short in this platform?**
A: No. The platform enforces a strictly long/flat constraint to model realistic unleveraged capital allocation.

**Q9: How easily can I add a new strategy?**
A: Extremely easily. You simply subclass `BaseStrategy`, implement the `generate_positions` vectorized method, and add the `@register_strategy` decorator.

**Q10: Why did you choose Parquet for caching?**
A: Parquet is a columnar storage format that is incredibly fast for reading time-series OHLCV data into pandas compared to SQLite or CSV, allowing instant dashboard loads.
