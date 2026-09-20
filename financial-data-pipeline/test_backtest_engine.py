"""
Unit tests for the Backtesting Engine (Layer 4).

All tests use small, deterministic, in-memory DataFrames.
No Supabase connection is required.

Run with:
    pytest test_backtest_engine.py -v
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backtest_engine import (
    calculate_max_drawdown,
    calculate_performance_metrics,
    execute_buy,
    execute_sell,
    run_buy_and_hold,
    run_strategy_backtest,
    validate_backtest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dates(n: int, start: str = "2020-01-02") -> list[date]:
    base = date.fromisoformat(start)
    return [base + timedelta(days=i) for i in range(n)]


def _make_prices(
    n: int,
    open_prices: list[float] | None = None,
    close_prices: list[float] | None = None,
) -> pd.DataFrame:
    """Minimal price DataFrame with open and close columns."""
    dates = _dates(n)
    opens  = open_prices  if open_prices  is not None else [100.0 + i for i in range(n)]
    closes = close_prices if close_prices is not None else [101.0 + i for i in range(n)]
    return pd.DataFrame({"date": dates, "open": opens, "close": closes})


def _make_data(
    opens: list[float],
    closes: list[float],
    signals: list[int | None],
) -> pd.DataFrame:
    """Merged price + signal DataFrame for run_strategy_backtest."""
    n = len(opens)
    assert len(closes) == n and len(signals) == n
    return pd.DataFrame({
        "date":   _dates(n),
        "open":   opens,
        "close":  closes,
        "signal": [float("nan") if s is None else float(s) for s in signals],
    })


# ===========================================================================
# 1. Buy execution
# ===========================================================================


class TestExecuteBuy:
    def test_units_equals_cash_over_exec_price_times_one_plus_tc(self):
        """units = cash / (exec_price * (1 + tc_rate))"""
        result = execute_buy(cash=10_000, open_price=100, slippage=0.0, tc_rate=0.001)
        expected_exec  = 100.0
        expected_units = 10_000 / (expected_exec * 1.001)
        assert abs(result["units"] - expected_units) < 1e-9

    def test_total_spent_equals_cash(self):
        """trade_value + transaction_cost must equal the original cash (≈0 remaining)."""
        cash = 50_000.0
        result = execute_buy(cash=cash, open_price=250.0, slippage=0.0, tc_rate=0.001)
        total_spent = result["trade_value"] + result["transaction_cost"]
        assert abs(total_spent - cash) < 1e-6

    def test_cash_after_is_zero_with_100pct_allocation(self):
        """Cash after 100% buy should be effectively zero."""
        result = execute_buy(cash=100_000, open_price=500, slippage=0.0, tc_rate=0.001)
        assert result["cash_after"] < 1e-6

    def test_slippage_increases_buy_price(self):
        """BUY execution price = open * (1 + slippage)."""
        result = execute_buy(cash=1_000, open_price=100, slippage=0.01, tc_rate=0.0)
        assert abs(result["exec_price"] - 101.0) < 1e-9

    def test_zero_slippage_zero_tc(self):
        """With zero costs, units = cash / open."""
        result = execute_buy(cash=10_000, open_price=100, slippage=0.0, tc_rate=0.0)
        assert abs(result["units"] - 100.0) < 1e-9


# ===========================================================================
# 2. Sell execution
# ===========================================================================


class TestExecuteSell:
    def test_proceeds_equals_sell_value_minus_tc(self):
        """proceeds = trade_value - transaction_cost."""
        result = execute_sell(units=10, open_price=110, slippage=0.0, tc_rate=0.001)
        expected_tv = 10 * 110.0
        expected_tc = expected_tv * 0.001
        assert abs(result["trade_value"] - expected_tv) < 1e-9
        assert abs(result["transaction_cost"] - expected_tc) < 1e-9
        assert abs(result["proceeds"] - (expected_tv - expected_tc)) < 1e-9

    def test_slippage_decreases_sell_price(self):
        """SELL execution price = open * (1 - slippage)."""
        result = execute_sell(units=5, open_price=100, slippage=0.01, tc_rate=0.0)
        assert abs(result["exec_price"] - 99.0) < 1e-9

    def test_zero_costs_full_cash(self):
        """No slippage, no TC: proceeds = units × open."""
        result = execute_sell(units=10, open_price=200, slippage=0.0, tc_rate=0.0)
        assert abs(result["proceeds"] - 2_000.0) < 1e-9


# ===========================================================================
# 3. Transaction cost calculation
# ===========================================================================


class TestTransactionCost:
    def test_buy_tc_is_rate_times_value(self):
        result = execute_buy(cash=10_000, open_price=100, slippage=0.0, tc_rate=0.002)
        # trade_value + tc = cash; tc = trade_value * 0.002
        # → trade_value * 1.002 = 10_000 → trade_value = 10_000/1.002
        expected_tv = 10_000 / 1.002
        expected_tc = expected_tv * 0.002
        assert abs(result["transaction_cost"] - expected_tc) < 1e-6

    def test_sell_tc_is_rate_times_value(self):
        result = execute_sell(units=10, open_price=100, slippage=0.0, tc_rate=0.005)
        assert abs(result["transaction_cost"] - 10 * 100 * 0.005) < 1e-9

    def test_zero_tc(self):
        buy  = execute_buy(cash=10_000,  open_price=100, slippage=0.0, tc_rate=0.0)
        sell = execute_sell(units=10, open_price=100, slippage=0.0, tc_rate=0.0)
        assert buy["transaction_cost"]  == 0.0
        assert sell["transaction_cost"] == 0.0


# ===========================================================================
# 4. Position tracking
# ===========================================================================


class TestPositionTracking:
    def test_position_becomes_1_after_long_signal(self):
        """Signal=1 on day 0 → BUY on day 1 → position=1 from day 1."""
        data = _make_data(
            opens=[100, 102, 104],
            closes=[101, 103, 105],
            signals=[1, 1, None],
        )
        equity_df, _ = run_strategy_backtest(data, 10_000, 0.001, 0.0)
        assert equity_df["position"].iloc[0] == 0   # not yet bought on day 0
        assert equity_df["position"].iloc[1] == 1   # bought at day 1 open
        assert equity_df["position"].iloc[2] == 1   # still long

    def test_position_becomes_0_after_exit_signal(self):
        """Signal=-1 on day 2 → SELL on day 3 → position=0 from day 3."""
        data = _make_data(
            opens=[100, 102, 104, 106],
            closes=[101, 103, 105, 107],
            signals=[1, None, -1, None],
        )
        equity_df, _ = run_strategy_backtest(data, 10_000, 0.001, 0.0)
        assert equity_df["position"].iloc[1] == 1   # bought on day 1
        assert equity_df["position"].iloc[2] == 1   # still long on exit-signal day
        assert equity_df["position"].iloc[3] == 0   # sold at day 3 open

    def test_flat_signal_while_long_keeps_position(self):
        """Signal=0 while long must NOT trigger a sell (FLAT != EXIT)."""
        data = _make_data(
            opens=[100, 102, 104, 106],
            closes=[101, 103, 105, 107],
            signals=[1, 0, 0, 0],    # FLAT after entry
        )
        equity_df, trades = run_strategy_backtest(data, 10_000, 0.001, 0.0)
        # Should be long from day 1 through end
        for i in range(1, 4):
            assert equity_df["position"].iloc[i] == 1
        # No completed trade (position still open)
        closed = [t for t in trades if t["status"] == "CLOSED"]
        assert len(closed) == 0

    def test_repeated_long_signals_do_not_create_repeated_buys(self):
        """Consecutive LONG signals while already long must not re-buy."""
        data = _make_data(
            opens=[100, 102, 104, 106, 108],
            closes=[101, 103, 105, 107, 109],
            signals=[1, 1, 1, 1, -1],
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.001, 0.0)
        all_entries = [t for t in trades]
        assert len(all_entries) == 1, "Must be exactly 1 trade (1 entry)"

    def test_exit_while_flat_does_nothing(self):
        """EXIT(-1) while already flat must not create any trade."""
        data = _make_data(
            opens=[100, 102, 104],
            closes=[101, 103, 105],
            signals=[-1, -1, -1],
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.001, 0.0)
        assert len(trades) == 0


# ===========================================================================
# 5. Portfolio value calculation
# ===========================================================================


class TestPortfolioValue:
    def test_portfolio_value_is_cash_plus_market_value(self):
        """portfolio_value = cash + units × close_price for every row."""
        data = _make_data(
            opens=[100, 102, 104],
            closes=[101, 103, 105],
            signals=[1, None, None],
        )
        equity_df, _ = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        for _, row in equity_df.iterrows():
            expected = row["cash"] + row["units"] * row["close_price"]
            assert abs(row["portfolio_value"] - expected) < 1e-6

    def test_initial_portfolio_value_equals_capital(self):
        """Before any trade, portfolio_value == initial_capital."""
        data = _make_data(
            opens=[100, 102],
            closes=[100, 102],
            signals=[None, None],   # no signals
        )
        equity_df, _ = run_strategy_backtest(data, 50_000, 0.001, 0.0)
        assert abs(equity_df["portfolio_value"].iloc[0] - 50_000) < 1e-6


# ===========================================================================
# 6. P&L calculation
# ===========================================================================


class TestPnL:
    def test_gross_pnl(self):
        """gross_pnl = exit_value - entry_value."""
        data = _make_data(
            opens=[100, 100, 110, 110],
            closes=[100, 109, 109, 120],
            signals=[1, None, -1, None],
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        closed = [t for t in trades if t["status"] == "CLOSED"]
        assert len(closed) == 1
        t = closed[0]
        expected_gross = t["exit_value"] - t["entry_value"]
        assert abs(t["gross_pnl"] - expected_gross) < 1e-6

    def test_net_pnl_accounts_for_both_costs(self):
        """net_pnl = gross_pnl - entry_tc - exit_tc."""
        data = _make_data(
            opens=[100, 100, 110, 110],
            closes=[100, 109, 109, 120],
            signals=[1, None, -1, None],
        )
        tc_rate = 0.001
        _, trades = run_strategy_backtest(data, 10_000, tc_rate, 0.0)
        closed = [t for t in trades if t["status"] == "CLOSED"]
        t = closed[0]
        expected_net = t["gross_pnl"] - t["entry_tc"] - t["exit_tc"]
        assert abs(t["net_pnl"] - expected_net) < 1e-6

    def test_zero_cost_net_equals_gross(self):
        """With tc_rate=0 and slippage=0, net_pnl == gross_pnl."""
        data = _make_data(
            opens=[100, 100, 110, 110],
            closes=[100, 109, 109, 115],
            signals=[1, None, -1, None],
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        closed = [t for t in trades if t["status"] == "CLOSED"]
        t = closed[0]
        assert abs(t["net_pnl"] - t["gross_pnl"]) < 1e-9


# ===========================================================================
# 7. Signal → next-day execution
# ===========================================================================


class TestSignalNextDayExecution:
    def test_buy_executes_on_next_day_open(self):
        """LONG signal on day 0 must execute at day 1 OPEN, not day 0 close."""
        data = _make_data(
            opens= [100,  105,  110],
            closes=[101,  106,  111],
            signals=[1,  None, None],
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        assert len(trades) == 1
        t = trades[0]
        # Entry must be on date index 1 (day 1) at open=105
        assert t["entry_date"] == _dates(3)[1]
        assert abs(t["entry_price"] - 105.0) < 1e-9

    def test_sell_executes_on_next_day_open(self):
        """EXIT signal on day 2 must execute at day 3 OPEN."""
        data = _make_data(
            opens= [100, 105, 108, 112],
            closes=[101, 106, 109, 113],
            signals=[1, None, -1, None],
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        closed = [t for t in trades if t["status"] == "CLOSED"]
        assert len(closed) == 1
        t = closed[0]
        assert t["exit_date"] == _dates(4)[3]
        assert abs(t["exit_price"] - 112.0) < 1e-9


# ===========================================================================
# 8. Look-ahead bias prevention
# ===========================================================================


class TestLookaheadBias:
    def test_execution_date_after_signal_date(self):
        """validate_backtest must pass when entry_date > signal_date."""
        data = _make_data(
            opens=[100, 105, 108, 112],
            closes=[101, 106, 109, 113],
            signals=[1, None, -1, None],
        )
        equity_df, trades = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        # Should not raise
        validate_backtest(data, equity_df, trades)

    def test_validate_raises_if_execution_same_as_signal(self):
        """validate_backtest must raise ValueError on look-ahead bias."""
        equity_df = pd.DataFrame({
            "date":            _dates(3),
            "cash":            [10_000.0] * 3,
            "units":           [0.0] * 3,
            "close_price":     [100.0, 105.0, 110.0],
            "market_value":    [0.0] * 3,
            "portfolio_value": [10_000.0] * 3,
            "position":        [0, 0, 0],
        })
        data_df = pd.DataFrame({
            "date": _dates(3),
            "open": [100.0, 105.0, 110.0],
            "close":[101.0, 106.0, 111.0],
            "signal": [1.0, float("nan"), float("nan")],
        })
        bad_trade = {
            "signal_date": _dates(3)[1],
            "entry_date":  _dates(3)[1],  # same as signal_date → look-ahead!
            "entry_price": 105.0,
            "units": 10.0,
            "entry_value": 1050.0,
            "entry_tc": 0.0,
            "status": "CLOSED",
            "exit_date": _dates(3)[2],
            "exit_price": 110.0,
        }
        with pytest.raises(ValueError, match="Look-ahead"):
            validate_backtest(data_df, equity_df, [bad_trade])


# ===========================================================================
# 9. Buy-and-Hold calculation
# ===========================================================================


class TestBuyAndHold:
    def test_bh_starts_fully_invested(self):
        """B&H: almost all capital goes into units at first open price."""
        prices = _make_prices(5, open_prices=[100] * 5, close_prices=[100] * 5)
        equity_df, entry_tc = run_buy_and_hold(prices, 10_000, 0.001, 0.0)
        # portfolio_value on all days should be ~cash + units*100 ≈ 10_000 - tc
        assert equity_df["portfolio_value"].iloc[0] < 10_000  # tc was deducted
        assert equity_df["portfolio_value"].iloc[0] > 9_900   # but not much

    def test_bh_increases_with_price(self):
        """B&H portfolio value tracks close price after entry."""
        closes = [100.0, 110.0, 120.0, 115.0, 130.0]
        prices = _make_prices(5, open_prices=[100] * 5, close_prices=closes)
        equity_df, _ = run_buy_and_hold(prices, 10_000, 0.0, 0.0)
        # Ratio of pv should track ratio of close prices
        pv = equity_df["portfolio_value"].tolist()
        # At zero costs, pv[i] = 10_000 * closes[i] / 100
        for i, c in enumerate(closes):
            expected = 10_000 * c / 100
            assert abs(pv[i] - expected) < 1e-3


# ===========================================================================
# 10. Maximum drawdown
# ===========================================================================


class TestMaxDrawdown:
    def test_known_drawdown(self):
        """[100, 150, 75] → drawdown = 75/150 - 1 = -0.5"""
        result = calculate_max_drawdown([100.0, 150.0, 75.0], _dates(3))
        assert abs(result["max_drawdown"] - (-0.5)) < 1e-9

    def test_monotone_increase_no_drawdown(self):
        """Strictly increasing values: drawdown = 0."""
        result = calculate_max_drawdown([100.0, 110.0, 120.0], _dates(3))
        assert result["max_drawdown"] == 0.0

    def test_drawdown_always_le_zero(self):
        import random
        random.seed(42)
        vals = [100.0]
        for _ in range(50):
            vals.append(vals[-1] * (1 + random.uniform(-0.05, 0.07)))
        result = calculate_max_drawdown(vals, _dates(len(vals)))
        assert result["max_drawdown"] <= 0.0

    def test_trough_date_identified(self):
        """Trough date must be the index of the minimum portfolio value."""
        vals = [100.0, 90.0, 60.0, 80.0, 70.0]
        dates = _dates(5)
        result = calculate_max_drawdown(vals, dates)
        assert result["max_drawdown_trough_date"] == dates[2]


# ===========================================================================
# 11. Strategy and benchmark use identical periods
# ===========================================================================


class TestIdenticalPeriods:
    def test_same_dates_used(self):
        """B&H and strategy backtest must operate on the same date range."""
        opens  = [100.0, 105.0, 110.0, 108.0, 115.0]
        closes = [101.0, 106.0, 111.0, 109.0, 116.0]
        sigs   = [1, None, None, -1, None]

        prices = _make_prices(5, open_prices=opens, close_prices=closes)
        data   = _make_data(opens, closes, sigs)

        strategy_eq, _ = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        bh_eq, _       = run_buy_and_hold(prices, 10_000, 0.0, 0.0)

        assert list(strategy_eq["date"]) == list(bh_eq["date"]), (
            "Strategy and B&H must cover the same date range for fair comparison."
        )


# ===========================================================================
# 12. Repeated signals don't create repeated trades
# ===========================================================================


class TestRepeatedSignals:
    def test_consecutive_longs_one_trade(self):
        data = _make_data(
            opens= [100, 102, 104, 106, 108],
            closes=[101, 103, 105, 107, 109],
            signals=[1, 1, 1, 1, None],
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        assert len(trades) == 1

    def test_consecutive_exits_while_flat_no_trades(self):
        data = _make_data(
            opens= [100, 102, 104],
            closes=[101, 103, 105],
            signals=[-1, -1, -1],
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        assert len(trades) == 0


# ===========================================================================
# 13. Open position at end handled correctly
# ===========================================================================


class TestOpenPositionAtEnd:
    def test_open_position_recorded_not_executed(self):
        """If the backtest ends while long, trade status must be OPEN."""
        data = _make_data(
            opens=[100, 102, 104],
            closes=[101, 103, 105],
            signals=[1, None, None],  # buy day 0, never exit
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.001, 0.0)
        assert len(trades) == 1
        assert trades[0]["status"] == "OPEN"
        assert trades[0]["exit_date"] is None
        assert trades[0]["net_pnl"]   is None

    def test_last_day_pending_sell_not_executed(self):
        """EXIT signal on the last day must NOT be executed (no next day)."""
        data = _make_data(
            opens=[100, 102, 104],
            closes=[101, 103, 105],
            signals=[1, None, -1],   # exit signal on last day → can't execute
        )
        _, trades = run_strategy_backtest(data, 10_000, 0.0, 0.0)
        # Position was entered; exit signal on last day has no execution date
        statuses = {t["status"] for t in trades}
        assert "OPEN" in statuses
        assert "CLOSED" not in statuses


# ===========================================================================
# 14. Cash never negative
# ===========================================================================


class TestCashNeverNegative:
    def test_cash_always_nonnegative(self):
        """Cash must never go below zero regardless of trading pattern."""
        opens  = [100 + i * 2 for i in range(20)]
        closes = [101 + i * 2 for i in range(20)]
        # Alternating long/exit
        signals = [1 if i % 4 in (0, 1) else -1 if i % 4 == 2 else None for i in range(20)]
        data = _make_data(opens, closes, signals)
        equity_df, _ = run_strategy_backtest(data, 10_000, 0.001, 0.0)
        assert (equity_df["cash"] >= -1e-8).all()

    def test_validate_raises_on_negative_cash(self):
        equity_df = pd.DataFrame({
            "date":            _dates(2),
            "cash":            [10_000.0, -0.01],  # negative!
            "units":           [0.0, 0.0],
            "close_price":     [100.0, 100.0],
            "market_value":    [0.0, 0.0],
            "portfolio_value": [10_000.0, 9_999.99],
            "position":        [0, 0],
        })
        data_df = pd.DataFrame({
            "date": _dates(2),
            "open": [100.0, 100.0],
            "close":[100.0, 100.0],
            "signal": [float("nan"), float("nan")],
        })
        with pytest.raises(ValueError, match="negative"):
            validate_backtest(data_df, equity_df, [])


# ===========================================================================
# 15. Fractional units
# ===========================================================================


class TestFractionalUnits:
    def test_high_price_asset_fractional_units(self):
        """BTC at $50,000 with $100 capital must give fractional units."""
        result = execute_buy(cash=100.0, open_price=50_000.0, slippage=0.0, tc_rate=0.0)
        assert result["units"] == pytest.approx(0.002, abs=1e-9)

    def test_fractional_units_in_backtest(self):
        """run_strategy_backtest must support fractional units (BTC-style)."""
        opens  = [50_000.0, 51_000.0, 52_000.0]
        closes = [50_100.0, 51_100.0, 52_100.0]
        data = _make_data(opens, closes, signals=[1, None, None])
        equity_df, trades = run_strategy_backtest(data, 100.0, 0.0, 0.0)
        if trades:
            assert trades[0]["units"] < 1.0   # fractional
        # Portfolio value should be positive throughout
        assert (equity_df["portfolio_value"] > 0).all()
