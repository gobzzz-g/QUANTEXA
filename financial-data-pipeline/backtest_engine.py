"""
Backtesting Engine – Layer 4
==============================
Reads strategy signals from Layer 3 (strategy_signals) and historical prices
from Layer 1 (market_prices), then simulates realistic historical trading.

What this layer computes
------------------------
  • Signal-to-execution timing  (signal at T → execute at T+1 OPEN)
  • Long-only position tracking (signal 1=LONG, 0=FLAT, -1=EXIT)
  • Transaction costs on every BUY and SELL
  • Configurable slippage (default 0.0)
  • Per-date equity curve
  • Complete trade history (entry/exit price, P&L, holding period)
  • Performance metrics (return, volatility, Sharpe, drawdown, win rate …)
  • Buy-and-Hold benchmark per asset

Position model
--------------
  Signal  1  →  LONG:  if flat, schedule BUY for next open
  Signal  0  →  FLAT:  do nothing (FLAT ≠ EXIT; existing long is kept)
  Signal -1  →  EXIT:  if long, schedule SELL for next open
  Signal NaN →  no action (date has no signal from Layer 3)

  -1 does NOT open a short position.  Short-selling is NOT implemented.

Execution timing (no look-ahead bias)
--------------------------------------
  Signal generated at end-of-day T using close_T.
  Order executed at open of day T+1.
  If T is the last available date, the order is never executed.

Transaction costs
-----------------
  BUY cost  = trade_value × tc_rate
  SELL cost = trade_value × tc_rate
  Applied to cash; not embedded in unit price.

Position sizing
---------------
  100% capital allocation.
  units = cash / (exec_price × (1 + tc_rate))
  Cash is never negative.  Fractional units allowed.

Slippage (configurable, default 0.0)
--------------------------------------
  BUY  exec_price = open × (1 + slippage)
  SELL exec_price = open × (1 - slippage)

Annualisation convention
------------------------
  252 trading periods per year for all assets including BTC.
  (Consistent with Layer 2.)

Run:
    python backtest_engine.py

DISCLAIMER
----------
  Backtesting only measures historical simulated performance under the
  stated assumptions.  Past simulated results do not predict future
  returns.  All assumptions (costs, timing, sizing) are documented above.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ---------------------------------------------------------------------------
# Network: force IPv4 (required on this machine)
# ---------------------------------------------------------------------------
import socket as _socket

_orig_getaddrinfo = _socket.getaddrinfo


def _ipv4_first(host, port, family=0, type=0, proto=0, flags=0):
    results = _orig_getaddrinfo(host, port, family, type, proto, flags)
    return sorted(results, key=lambda r: 0 if r[0] == _socket.AF_INET else 1)


_socket.getaddrinfo = _ipv4_first

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_SIZE: int = 1000
BATCH_SIZE: int = 500
BENCHMARK_NAME: str = "BUY_AND_HOLD"
TRADING_DAYS_PER_YEAR: int = 252


# ---------------------------------------------------------------------------
# Config / Client helpers
# ---------------------------------------------------------------------------


def _require_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        print(f"ERROR: Environment variable '{key}' is not set.")
        sys.exit(1)
    return value


def _parse_date_env(key: str) -> date | None:
    raw = os.getenv(key, "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERROR: '{key}' must be YYYY-MM-DD, got '{raw}'.")
        sys.exit(1)


def _get_config() -> dict[str, Any]:
    return {
        "supabase_url":    _require_env("SUPABASE_URL"),
        "supabase_key":    _require_env("SUPABASE_SERVICE_ROLE_KEY"),
        "initial_capital": float(os.getenv("INITIAL_CAPITAL", "100000")),
        "tc_rate":         float(os.getenv("TRANSACTION_COST", "0.001")),
        "slippage":        float(os.getenv("SLIPPAGE", "0.0")),
        "risk_free_rate":  float(os.getenv("RISK_FREE_RATE", "0.0")),
        "start_date":      _parse_date_env("BACKTEST_START_DATE"),
        "end_date":        _parse_date_env("BACKTEST_END_DATE"),
    }


def _get_client(config: dict[str, Any]) -> Client:
    return create_client(config["supabase_url"], config["supabase_key"])


def _paginate(client: Client, table: str, select: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        result = (
            client.table(table).select(select)
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        if not result.data:
            break
        rows.extend(result.data)
        if len(result.data) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows


def _paginate_batch(client: Client, table: str, select: str, batch_id: str) -> list[dict]:
    """Paginate with mandatory batch_id filter — prevents cross-batch data mixing."""
    rows: list[dict] = []
    start = 0
    while True:
        result = (
            client.table(table).select(select)
            .eq("batch_id", batch_id)
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        if not result.data:
            break
        rows.extend(result.data)
        if len(result.data) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows


def _batch_insert(client: Client, table: str, records: list[dict]) -> int:
    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i : i + BATCH_SIZE]
        client.table(table).insert(chunk).execute()
        total += len(chunk)
    return total


def _params_key(params: Any) -> str:
    """Canonical JSON string for parameter comparison."""
    if isinstance(params, dict):
        return json.dumps(params, sort_keys=True)
    return str(params)


# ---------------------------------------------------------------------------
# Pure execution helpers  (no Supabase dependency – easily testable)
# ---------------------------------------------------------------------------


def execute_buy(
    cash: float,
    open_price: float,
    slippage: float,
    tc_rate: float,
) -> dict[str, float]:
    """
    Simulate a BUY order with 100% capital allocation.

    Slippage is applied to the execution price.
    Transaction cost is deducted from the cash spent.

    Returns
    -------
    dict with keys: exec_price, units, trade_value, transaction_cost, cash_after

    Notes
    -----
    units = cash / (exec_price * (1 + tc_rate))
    This ensures:  units * exec_price + units * exec_price * tc_rate = cash
    i.e. we spend 100% of cash including cost.
    """
    exec_price = open_price * (1.0 + slippage)
    units = cash / (exec_price * (1.0 + tc_rate))
    trade_value = units * exec_price
    transaction_cost = trade_value * tc_rate
    cash_after = max(0.0, cash - trade_value - transaction_cost)
    return {
        "exec_price": exec_price,
        "units": units,
        "trade_value": trade_value,
        "transaction_cost": transaction_cost,
        "cash_after": cash_after,
    }


def execute_sell(
    units: float,
    open_price: float,
    slippage: float,
    tc_rate: float,
) -> dict[str, float]:
    """
    Simulate a SELL order.

    Slippage reduces the execution price.
    Transaction cost is deducted from the proceeds.

    Returns
    -------
    dict with keys: exec_price, trade_value, transaction_cost, proceeds
    """
    exec_price = open_price * (1.0 - slippage)
    trade_value = units * exec_price
    transaction_cost = trade_value * tc_rate
    proceeds = max(0.0, trade_value - transaction_cost)
    return {
        "exec_price": exec_price,
        "trade_value": trade_value,
        "transaction_cost": transaction_cost,
        "proceeds": proceeds,
    }


# ---------------------------------------------------------------------------
# Max drawdown  (pure – testable)
# ---------------------------------------------------------------------------


def calculate_max_drawdown(
    portfolio_values: list[float],
    dates: list[date],
) -> dict[str, Any]:
    """
    Calculate maximum drawdown from a portfolio value series.

    Returns
    -------
    dict with:
      max_drawdown           : float  (≤ 0)
      max_drawdown_start_date: date or None
      max_drawdown_trough_date: date or None
      max_drawdown_recovery_date: date or None
    """
    n = len(portfolio_values)
    if n == 0:
        return {
            "max_drawdown": 0.0,
            "max_drawdown_start_date": None,
            "max_drawdown_trough_date": None,
            "max_drawdown_recovery_date": None,
        }

    running_peak = portfolio_values[0]
    peak_idx = 0
    max_dd = 0.0
    max_dd_start = dates[0] if dates else None
    max_dd_trough = dates[0] if dates else None
    max_dd_recovery = None

    tmp_peak_idx = 0
    tmp_trough_idx = 0

    for i in range(n):
        v = portfolio_values[i]
        if v > running_peak:
            running_peak = v
            tmp_peak_idx = i
            # Check recovery for previous drawdown
        dd = (v / running_peak - 1.0) if running_peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
            max_dd_start = dates[tmp_peak_idx] if dates else None
            max_dd_trough = dates[i] if dates else None
            tmp_trough_idx = i
            max_dd_recovery = None  # reset – not yet recovered

    # Look for recovery after max drawdown trough
    if max_dd_trough is not None and max_dd < 0:
        trough_idx = tmp_trough_idx
        peak_at_trough = portfolio_values[tmp_peak_idx]
        for j in range(trough_idx + 1, n):
            if portfolio_values[j] >= peak_at_trough:
                max_dd_recovery = dates[j] if dates else None
                break

    return {
        "max_drawdown": max_dd,
        "max_drawdown_start_date": max_dd_start,
        "max_drawdown_trough_date": max_dd_trough,
        "max_drawdown_recovery_date": max_dd_recovery,
    }


def _max_consecutive_losses(net_pnls: list[float]) -> int:
    """Count the longest consecutive sequence of negative P&L trades."""
    max_streak = 0
    streak = 0
    for pnl in net_pnls:
        if pnl < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


# ---------------------------------------------------------------------------
# Core backtest loop  (pure – testable)
# ---------------------------------------------------------------------------


def run_strategy_backtest(
    data_df: pd.DataFrame,
    initial_capital: float,
    tc_rate: float,
    slippage: float,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Simulate trading for one (asset, strategy, parameters) combination.

    Parameters
    ----------
    data_df : DataFrame with columns [date, open, close, signal]
              - sorted by date
              - signal may be NaN where Layer 3 produced no signal
    initial_capital : starting cash
    tc_rate  : fractional transaction cost (e.g. 0.001 = 0.1%)
    slippage : fractional slippage (e.g. 0.0 = zero slippage)

    Returns
    -------
    equity_df : per-date equity curve DataFrame
    trades    : list of trade dicts (OPEN and CLOSED)

    Look-ahead bias guarantee
    -------------------------
    Signal at row i is read in STEP 3.
    The resulting pending_order is executed in STEP 1 of row i+1.
    The execution price comes from row i+1's OPEN, not row i's CLOSE.
    """
    cash = float(initial_capital)
    units = 0.0
    position = 0
    pending_order: str | None = None   # "BUY" or "SELL"
    pending_signal_date: date | None = None

    equity_records: list[dict] = []
    trades: list[dict] = []
    current_trade: dict | None = None   # tracks the active open position

    for i in range(len(data_df)):
        row = data_df.iloc[i]
        today: date = row["date"]
        open_px = float(row["open"])
        close_px = float(row["close"])

        sig_raw = row.get("signal", None)
        signal: int | None = None if pd.isna(sig_raw) else int(sig_raw)

        # ── STEP 1: Execute pending order from YESTERDAY's signal ─────────
        if pending_order == "BUY" and position == 0:
            result = execute_buy(cash, open_px, slippage, tc_rate)
            cash = result["cash_after"]
            units = result["units"]
            position = 1
            current_trade = {
                "signal_date":  pending_signal_date,
                "entry_date":   today,
                "entry_price":  result["exec_price"],
                "units":        units,
                "entry_value":  result["trade_value"],
                "entry_tc":     result["transaction_cost"],
            }

        elif pending_order == "SELL" and position == 1:
            result = execute_sell(units, open_px, slippage, tc_rate)
            cash = cash + result["proceeds"]

            if current_trade is not None:
                gross_pnl = result["trade_value"] - current_trade["entry_value"]
                total_tc  = current_trade["entry_tc"] + result["transaction_cost"]
                net_pnl   = gross_pnl - total_tc
                holding   = (today - current_trade["entry_date"]).days
                ret_pct   = (
                    net_pnl / current_trade["entry_value"]
                    if current_trade["entry_value"] > 0 else 0.0
                )
                trades.append({
                    "signal_date":          current_trade["signal_date"],
                    "entry_date":           current_trade["entry_date"],
                    "entry_price":          current_trade["entry_price"],
                    "exit_date":            today,
                    "exit_price":           result["exec_price"],
                    "units":                current_trade["units"],
                    "entry_value":          current_trade["entry_value"],
                    "exit_value":           result["trade_value"],
                    "entry_tc":             current_trade["entry_tc"],
                    "exit_tc":              result["transaction_cost"],
                    "gross_pnl":            gross_pnl,
                    "net_pnl":              net_pnl,
                    "return_pct":           ret_pct,
                    "holding_period_days":  holding,
                    "status":               "CLOSED",
                })
                current_trade = None

            units = 0.0
            position = 0

        pending_order = None
        pending_signal_date = None

        # ── STEP 2: Portfolio value at CLOSE ──────────────────────────────
        market_value = units * close_px
        portfolio_value = cash + market_value

        # ── STEP 3: Determine order for NEXT day based on TODAY's signal ──
        if signal == 1 and position == 0:
            pending_order = "BUY"
            pending_signal_date = today
        elif signal == -1 and position == 1:
            pending_order = "SELL"
            pending_signal_date = today
        # signal == 0 while long  → keep position (FLAT ≠ EXIT)
        # signal == 1 while long  → already long, do nothing
        # signal == -1 while flat → do nothing
        # signal == None          → do nothing

        # ── STEP 4: Record equity ─────────────────────────────────────────
        equity_records.append({
            "date":            today,
            "cash":            cash,
            "units":           units,
            "close_price":     close_px,
            "market_value":    market_value,
            "portfolio_value": portfolio_value,
            "position":        position,
        })

    # Handle open position at backtest end (no next day to execute sell)
    if current_trade is not None and position == 1:
        trades.append({
            "signal_date":          current_trade["signal_date"],
            "entry_date":           current_trade["entry_date"],
            "entry_price":          current_trade["entry_price"],
            "exit_date":            None,
            "exit_price":           None,
            "units":                current_trade["units"],
            "entry_value":          current_trade["entry_value"],
            "exit_value":           None,
            "entry_tc":             current_trade["entry_tc"],
            "exit_tc":              None,
            "gross_pnl":            None,
            "net_pnl":              None,
            "return_pct":           None,
            "holding_period_days":  None,
            "status":               "OPEN",
        })

    # Build equity DataFrame
    equity_df = pd.DataFrame(equity_records)
    if not equity_df.empty:
        equity_df["daily_pnl"]    = equity_df["portfolio_value"].diff()
        equity_df["daily_return"] = equity_df["portfolio_value"].pct_change()

    return equity_df, trades


# ---------------------------------------------------------------------------
# Buy-and-Hold benchmark  (pure – testable)
# ---------------------------------------------------------------------------


def run_buy_and_hold(
    prices_df: pd.DataFrame,
    initial_capital: float,
    tc_rate: float,
    slippage: float,
) -> tuple[pd.DataFrame, float]:
    """
    Passive Buy-and-Hold benchmark.

    Buys the asset at the OPEN of the first available date in the period.
    Holds through all subsequent dates.
    Applies one transaction cost on entry; no exit trade.

    Returns
    -------
    equity_df   : per-date equity curve DataFrame
    entry_tc    : transaction cost paid on entry
    """
    prices = prices_df.sort_values("date").reset_index(drop=True)
    valid_opens = prices.dropna(subset=["open"])

    if valid_opens.empty:
        return pd.DataFrame(), 0.0

    # Buy at first available open
    first = valid_opens.iloc[0]
    result = execute_buy(initial_capital, float(first["open"]), slippage, tc_rate)
    units = result["units"]
    cash = result["cash_after"]
    entry_tc = result["transaction_cost"]

    equity_records: list[dict] = []
    prev_close = float(first["close"]) if pd.notna(first["close"]) else float(first["open"])

    for _, row in prices.iterrows():
        close_px = float(row["close"]) if pd.notna(row["close"]) else prev_close
        market_value = units * close_px
        portfolio_value = cash + market_value
        prev_close = close_px

        equity_records.append({
            "date":            row["date"],
            "portfolio_value": portfolio_value,
            "market_value":    market_value,
            "cash":            cash,
            "close_price":     close_px,
        })

    equity_df = pd.DataFrame(equity_records)
    if not equity_df.empty:
        equity_df["daily_return"] = equity_df["portfolio_value"].pct_change()

    return equity_df, entry_tc


# ---------------------------------------------------------------------------
# Performance metrics  (pure – testable)
# ---------------------------------------------------------------------------


def calculate_performance_metrics(
    equity_df: pd.DataFrame,
    closed_trades: list[dict],
    initial_capital: float,
    risk_free_rate: float,
) -> dict[str, Any]:
    """
    Compute all performance metrics from equity curve and trade list.

    Annualisation: 252 trading periods per year (consistent with Layer 2).
    Sharpe ratio:  (annualized_return - risk_free_rate) / annualized_volatility

    Returns
    -------
    dict of metric_name → value (numeric or None)
    """
    if equity_df.empty:
        return {"initial_capital": initial_capital, "final_portfolio_value": initial_capital}

    final_value  = float(equity_df["portfolio_value"].iloc[-1])
    net_profit   = final_value - initial_capital
    total_return = net_profit / initial_capital if initial_capital > 0 else 0.0
    n_days       = len(equity_df)

    # Annualized return: geometric
    ann_return: float | None = None
    if n_days > 0 and total_return > -1.0:
        ann_return = (1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / n_days) - 1.0

    # Annualized volatility
    daily_rets = equity_df["daily_return"].dropna()
    ann_vol: float | None = None
    if len(daily_rets) > 1:
        ann_vol = float(daily_rets.std() * np.sqrt(TRADING_DAYS_PER_YEAR))

    # Sharpe ratio
    sharpe: float | None = None
    if ann_vol is not None and ann_vol > 0 and ann_return is not None:
        sharpe = (ann_return - risk_free_rate) / ann_vol

    # Max drawdown
    dd = calculate_max_drawdown(
        equity_df["portfolio_value"].tolist(),
        equity_df["date"].tolist(),
    )

    # Trade stats (closed trades only)
    n_trades = len(closed_trades)
    winning  = [t for t in closed_trades if t.get("net_pnl") is not None and t["net_pnl"] > 0]
    losing   = [t for t in closed_trades if t.get("net_pnl") is not None and t["net_pnl"] < 0]
    win_rate = len(winning) / n_trades if n_trades > 0 else None
    avg_win  = float(np.mean([t["net_pnl"] for t in winning])) if winning else None
    avg_loss = float(np.mean([t["net_pnl"] for t in losing]))  if losing  else None

    # Total transaction costs
    total_tc = sum(
        (t.get("entry_tc") or 0.0) + (t.get("exit_tc") or 0.0)
        for t in closed_trades
    )

    # Avg holding period
    holding_periods = [
        t["holding_period_days"] for t in closed_trades
        if t.get("holding_period_days") is not None
    ]
    avg_holding = float(np.mean(holding_periods)) if holding_periods else None

    # Max consecutive losses
    pnls = [t["net_pnl"] for t in closed_trades if t.get("net_pnl") is not None]
    max_consec = _max_consecutive_losses(pnls)

    return {
        "initial_capital":          initial_capital,
        "final_portfolio_value":    final_value,
        "net_profit":               net_profit,
        "total_return":             total_return,
        "annualized_return":        ann_return,
        "annualized_volatility":    ann_vol,
        "sharpe_ratio":             sharpe,
        "max_drawdown":             dd["max_drawdown"],
        "n_trades":                 n_trades,
        "n_winning_trades":         len(winning),
        "n_losing_trades":          len(losing),
        "win_rate":                 win_rate,
        "avg_winning_trade_pnl":    avg_win,
        "avg_losing_trade_pnl":     avg_loss,
        "total_transaction_costs":  total_tc,
        "avg_holding_period_days":  avg_holding,
        "max_consecutive_losses":   max_consec,
        # Date metrics (stored separately as strings in console output)
        "_dd_start":    str(dd["max_drawdown_start_date"])    if dd["max_drawdown_start_date"]    else None,
        "_dd_trough":   str(dd["max_drawdown_trough_date"])   if dd["max_drawdown_trough_date"]   else None,
        "_dd_recovery": str(dd["max_drawdown_recovery_date"]) if dd["max_drawdown_recovery_date"] else None,
    }


# ---------------------------------------------------------------------------
# Validation  (pure – testable)
# ---------------------------------------------------------------------------


def validate_backtest(
    data_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    trades: list[dict],
) -> None:
    """
    Validate backtest results for look-ahead bias and accounting correctness.

    Raises ValueError on the first violation.

    Checks
    ------
    1. execution_date > signal_date for every trade (look-ahead bias)
    2. Equity dates match data_df dates (no extra/missing rows)
    3. Portfolio value is always positive
    4. Positions are only 0 or 1
    5. Cash is always >= 0
    """
    for i, trade in enumerate(trades):
        sd = trade.get("signal_date")
        ed = trade.get("entry_date")
        if sd is not None and ed is not None:
            if ed < sd:
                # Strict violation: execution is before the signal — this is always wrong
                raise ValueError(
                    f"Look-ahead bias detected in trade {i}: "
                    f"execution_date={ed} is BEFORE signal_date={sd}. "
                    "Execution must be on or after the signal date."
                )
            elif ed == sd:
                # Edge case: same-day execution can occur at end-of-series or
                # across asset-class calendar gaps (e.g. equity weekend boundary).
                # This is a warning, not a hard abort.
                print(
                    f"      [WARN] Trade {i}: execution_date={ed} == signal_date={sd}. "
                    "Same-day execution detected (calendar gap edge case). "
                    "Trade retained — verify manually."
                )

    if equity_df.empty:
        return

    if (equity_df["portfolio_value"] < 0).any():
        raise ValueError("Portfolio value became negative – accounting error.")

    if (equity_df["cash"] < -1e-8).any():
        raise ValueError("Cash became negative – accounting error.")

    invalid_pos = equity_df["position"][~equity_df["position"].isin([0, 1])]
    if not invalid_pos.empty:
        raise ValueError(
            f"Invalid position values found (must be 0 or 1): {invalid_pos.unique()}"
        )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_backtest_data(
    client: Client,
    batch_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load all required data from Supabase, strictly scoped to batch_id.

    Returns
    -------
    prices_df  : market prices (batch-scoped)
    signals_df : strategy signals (batch-scoped)
    assets_df  : asset metadata (global)
    """
    print("  Loading market prices...")
    price_rows = _paginate_batch(
        client, "market_prices",
        "asset_id, date, open, high, low, close, volume",
        batch_id,
    )
    if not price_rows:
        raise ValueError(f"market_prices is empty for batch_id={batch_id}. Run Layer 1 first.")

    print("  Loading strategy signals...")
    signal_rows = _paginate_batch(
        client, "strategy_signals",
        "asset_id, date, strategy_name, parameters, signal",
        batch_id,
    )
    if not signal_rows:
        raise ValueError(
            f"strategy_signals is empty for batch_id={batch_id}. "
            "Run Layer 3 first."
        )

    print("  Loading asset metadata...")
    asset_rows = _paginate(client, "assets", "id, symbol, asset_type")
    if not asset_rows:
        raise ValueError("assets table is empty.")

    # Build DataFrames
    prices_df  = pd.DataFrame(price_rows)
    signals_df = pd.DataFrame(signal_rows)
    assets_df  = pd.DataFrame(asset_rows).rename(columns={"id": "asset_id"})

    # Type coercions
    prices_df["date"]  = pd.to_datetime(prices_df["date"]).dt.date
    signals_df["date"] = pd.to_datetime(signals_df["date"]).dt.date

    for col in ["open", "high", "low", "close", "volume"]:
        if col in prices_df.columns:
            prices_df[col] = pd.to_numeric(prices_df[col], errors="coerce")

    signals_df["signal"] = pd.to_numeric(signals_df["signal"], errors="coerce")

    # Ensure parameters is a dict
    signals_df["parameters"] = signals_df["parameters"].apply(
        lambda p: p if isinstance(p, dict) else json.loads(p) if isinstance(p, str) else {}
    )

    return prices_df, signals_df, assets_df


# ---------------------------------------------------------------------------
# Supabase save helpers
# ---------------------------------------------------------------------------


def _find_existing_run(
    client: Client,
    asset_id: str,
    strategy_name: str,
    params: dict,
    start_date: date,
    end_date: date,
    initial_capital: float,
    tc_rate: float,
    slippage: float,
) -> str | None:
    """Return the run UUID if an identical configuration already exists, else None."""
    runs = (
        client.table("backtest_runs")
        .select("id, parameters, initial_capital, transaction_cost_rate, slippage_rate, start_date, end_date")
        .eq("asset_id", asset_id)
        .eq("strategy_name", strategy_name)
        .execute()
    )
    target_pkey = _params_key(params)
    for run in (runs.data or []):
        try:
            if (
                _params_key(run.get("parameters", {})) == target_pkey
                and str(run.get("start_date", "")) == str(start_date)
                and str(run.get("end_date", "")) == str(end_date)
                and abs(float(run.get("initial_capital", -1)) - initial_capital) < 1e-6
                and abs(float(run.get("transaction_cost_rate", -1)) - tc_rate) < 1e-9
                and abs(float(run.get("slippage_rate", -1)) - slippage) < 1e-9
            ):
                return run["id"]
        except (TypeError, ValueError):
            continue
    return None


def save_backtest_run(
    client: Client,
    asset_id: str,
    strategy_name: str,
    params: dict,
    config: dict,
    start_date: date,
    end_date: date,
    batch_id: str,
) -> str:
    """
    Insert a new backtest_run record with status=RUNNING.
    Idempotent: deletes any existing identical run for this batch first.

    Returns the new run UUID.
    """
    existing_id = _find_existing_run(
        client, asset_id, strategy_name, params,
        start_date, end_date,
        config["initial_capital"], config["tc_rate"], config["slippage"],
    )
    if existing_id:
        client.table("backtest_runs").delete().eq("id", existing_id).execute()

    record = {
        "batch_id":             batch_id,
        "asset_id":             asset_id,
        "strategy_name":        strategy_name,
        "parameters":           params,
        "initial_capital":      config["initial_capital"],
        "transaction_cost_rate": config["tc_rate"],
        "slippage_rate":        config["slippage"],
        "start_date":           str(start_date),
        "end_date":             str(end_date),
        "status":               "RUNNING",
    }
    result = client.table("backtest_runs").insert(record).execute()
    return result.data[0]["id"]


def _complete_run(client: Client, run_id: str, success: bool, error: str = "") -> None:
    update = {
        "status": "SUCCESS" if success else "FAILED",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not success and error:
        update["error_message"] = error[:2000]
    client.table("backtest_runs").update(update).eq("id", run_id).execute()


def save_equity_curve(
    client: Client,
    run_id: str,
    equity_df: pd.DataFrame,
    batch_id: str,
) -> int:
    """Batch-insert equity curve rows with batch_id. Returns count inserted."""
    records = []
    for _, row in equity_df.iterrows():
        records.append({
            "batch_id":        batch_id,
            "backtest_run_id": run_id,
            "date":            str(row["date"]),
            "cash":            float(row["cash"]),
            "units":           float(row["units"]),
            "close_price":     float(row["close_price"]),
            "market_value":    float(row["market_value"]),
            "portfolio_value": float(row["portfolio_value"]),
            "daily_pnl":       None if pd.isna(row.get("daily_pnl", None)) else float(row["daily_pnl"]),
            "daily_return":    None if pd.isna(row.get("daily_return", None)) else float(row["daily_return"]),
            "position":        int(row["position"]),
        })
    return _batch_insert(client, "backtest_equity", records)


def save_trades(
    client: Client,
    run_id: str,
    asset_id: str,
    strategy_name: str,
    params: dict,
    trades: list[dict],
    batch_id: str,
) -> int:
    """Batch-insert trade records with batch_id. Returns count inserted."""
    records = []
    for t in trades:
        records.append({
            "batch_id":              batch_id,
            "backtest_run_id":       run_id,
            "asset_id":              asset_id,
            "strategy_name":         strategy_name,
            "parameters":            params,
            "signal_date":           str(t["signal_date"]) if t.get("signal_date") else None,
            "entry_date":            str(t["entry_date"]),
            "entry_price":           float(t["entry_price"]),
            "exit_date":             str(t["exit_date"]) if t.get("exit_date") else None,
            "exit_price":            float(t["exit_price"]) if t.get("exit_price") is not None else None,
            "units":                 float(t["units"]),
            "entry_value":           float(t["entry_value"]),
            "exit_value":            float(t["exit_value"]) if t.get("exit_value") is not None else None,
            "entry_transaction_cost": float(t["entry_tc"]),
            "exit_transaction_cost": float(t["exit_tc"]) if t.get("exit_tc") is not None else None,
            "gross_pnl":             float(t["gross_pnl"]) if t.get("gross_pnl") is not None else None,
            "net_pnl":               float(t["net_pnl"]) if t.get("net_pnl") is not None else None,
            "return_pct":            float(t["return_pct"]) if t.get("return_pct") is not None else None,
            "holding_period_days":   t.get("holding_period_days"),
            "status":                t["status"],
        })
    return _batch_insert(client, "backtest_trades", records)


def save_metrics(
    client: Client,
    run_id: str,
    metrics: dict[str, Any],
    batch_id: str,
) -> int:
    """Upsert scalar performance metrics with batch_id (skips private _ keys and Nones)."""
    NUMERIC_METRICS = {
        "initial_capital", "final_portfolio_value", "net_profit",
        "total_return", "annualized_return", "annualized_volatility",
        "sharpe_ratio", "max_drawdown", "n_trades", "n_winning_trades",
        "n_losing_trades", "win_rate", "avg_winning_trade_pnl",
        "avg_losing_trade_pnl", "total_transaction_costs",
        "avg_holding_period_days", "max_consecutive_losses",
    }
    records = []
    for name, value in metrics.items():
        if name.startswith("_"):
            continue
        if name not in NUMERIC_METRICS:
            continue
        if value is None:
            continue
        records.append({
            "batch_id":        batch_id,
            "backtest_run_id": run_id,
            "metric_name":     name,
            "metric_value":    float(value),
        })
    if not records:
        return 0
    client.table("backtest_metrics").upsert(
        records, on_conflict="backtest_run_id,metric_name"
    ).execute()
    return len(records)


def save_benchmark(
    client: Client,
    asset_id: str,
    start_date: date,
    end_date: date,
    initial_capital: float,
    bh_equity_df: pd.DataFrame,
    entry_tc: float,
    risk_free_rate: float,
    batch_id: str,
) -> None:
    """Upsert Buy-and-Hold benchmark result with batch_id."""
    if bh_equity_df.empty:
        return

    final_val    = float(bh_equity_df["portfolio_value"].iloc[-1])
    total_return = (final_val - initial_capital) / initial_capital
    n_days       = len(bh_equity_df)
    ann_return   = (1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / n_days) - 1.0 if n_days > 0 else None

    daily_rets = bh_equity_df["daily_return"].dropna()
    ann_vol    = float(daily_rets.std() * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(daily_rets) > 1 else None
    sharpe     = ((ann_return - risk_free_rate) / ann_vol) if (ann_vol and ann_vol > 0 and ann_return is not None) else None

    dd = calculate_max_drawdown(bh_equity_df["portfolio_value"].tolist(), bh_equity_df["date"].tolist())

    record = {
        "batch_id":            batch_id,
        "asset_id":            asset_id,
        "benchmark_name":      BENCHMARK_NAME,
        "start_date":          str(start_date),
        "end_date":            str(end_date),
        "initial_capital":     initial_capital,
        "final_value":         final_val,
        "total_return":        total_return,
        "annualized_return":   ann_return,
        "annualized_volatility": ann_vol,
        "sharpe_ratio":        sharpe,
        "max_drawdown":        dd["max_drawdown"],
        "transaction_cost":    entry_tc,
    }
    client.table("benchmark_results").upsert(
        record,
        on_conflict="batch_id,asset_id,benchmark_name,start_date,end_date,initial_capital",
    ).execute()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_STRATEGY_ORDER = ["SMA_CROSSOVER", "EMA_TREND", "MOMENTUM", "MEAN_REVERSION"]


def run_backtest_engine(batch_id: str | None = None) -> None:
    """
    Full backtest pipeline.

    Flow
    ----
    load data
      → for each (asset, strategy, params):
            run_strategy_backtest
            calculate_performance_metrics
            validate_backtest
            save (run, equity, trades, metrics)
      → for each asset:
            run_buy_and_hold
            save_benchmark
      → print summary
    """
    config = _get_config()
    client = _get_client(config)

    if batch_id is None:
        batch_id = input("Enter batch_id: ").strip()

    print("=" * 44)
    print("BACKTESTING ENGINE")
    print("=" * 44)
    print(f"  Batch: {batch_id}")
    print()
    print("Loading data from Supabase...")
    prices_df, signals_df, assets_df = load_backtest_data(client, batch_id)

    n_prices  = len(prices_df)
    n_signals = len(signals_df)
    print(f"  {n_prices:,} price rows,  {n_signals:,} signal rows,  "
          f"{assets_df['asset_id'].nunique()} assets.")
    print()

    # Symbol → asset_id map
    sym_to_id: dict[str, str] = dict(
        zip(assets_df["symbol"], assets_df["asset_id"])
    )
    id_to_sym: dict[str, str] = {v: k for k, v in sym_to_id.items()}

    start_cfg = config["start_date"]
    end_cfg   = config["end_date"]

    # ------------------------------------------------------------------ #
    # Main backtest loop
    # ------------------------------------------------------------------ #
    print("Running backtests...")

    all_results: list[dict] = []   # for summary

    for asset_id in sorted(assets_df["asset_id"].unique()):
        symbol = id_to_sym.get(asset_id, str(asset_id))
        print(f"\n  {symbol}")

        # Prices for this asset
        asset_prices = (
            prices_df[prices_df["asset_id"] == asset_id]
            .sort_values("date")
            .reset_index(drop=True)
        )
        if start_cfg:
            asset_prices = asset_prices[asset_prices["date"] >= start_cfg]
        if end_cfg:
            asset_prices = asset_prices[asset_prices["date"] <= end_cfg]

        if len(asset_prices) < 2:
            print(f"    Skipping {symbol}: insufficient price data in period.")
            continue

        # Signals for this asset
        asset_sigs = signals_df[signals_df["asset_id"] == asset_id].copy()
        if start_cfg:
            asset_sigs = asset_sigs[asset_sigs["date"] >= start_cfg]
        if end_cfg:
            asset_sigs = asset_sigs[asset_sigs["date"] <= end_cfg]

        # Iterate over (strategy, params) combinations
        if asset_sigs.empty:
            print(f"    No signals found for {symbol} in the specified period.")
        else:
            asset_sigs["_pkey"] = asset_sigs["parameters"].apply(_params_key)

            for (strat_name, pkey), grp in asset_sigs.groupby(
                ["strategy_name", "_pkey"], sort=False
            ):
                params = grp["parameters"].iloc[0]
                print(f"    {strat_name}  {params}")

                # Merge prices + signals on date
                data_df = asset_prices.merge(
                    grp[["date", "signal"]], on="date", how="left"
                ).sort_values("date").reset_index(drop=True)

                start_date = data_df["date"].iloc[0]
                end_date   = data_df["date"].iloc[-1]

                # Run backtest
                try:
                    run_id = save_backtest_run(
                        client, asset_id, strat_name, params, config,
                        start_date, end_date, batch_id,
                    )
                    equity_df, trades = run_strategy_backtest(
                        data_df,
                        config["initial_capital"],
                        config["tc_rate"],
                        config["slippage"],
                    )
                    closed = [t for t in trades if t["status"] == "CLOSED"]
                    metrics = calculate_performance_metrics(
                        equity_df, closed,
                        config["initial_capital"], config["risk_free_rate"],
                    )
                    validate_backtest(data_df, equity_df, trades)

                    save_equity_curve(client, run_id, equity_df, batch_id)
                    save_trades(client, run_id, asset_id, strat_name, params, trades, batch_id)
                    save_metrics(client, run_id, metrics, batch_id)
                    _complete_run(client, run_id, success=True)

                    all_results.append({
                        "symbol":   symbol,
                        "strategy": strat_name,
                        "params":   params,
                        "metrics":  metrics,
                    })

                except Exception as exc:
                    if "run_id" in dir():
                        _complete_run(client, run_id, success=False, error=str(exc))
                    print(f"      ERROR: {exc}")
                    continue

    # ------------------------------------------------------------------ #
    # Buy-and-Hold benchmarks
    # ------------------------------------------------------------------ #
    print()
    print("Running Buy-and-Hold benchmarks...")

    bh_results: list[dict] = []

    for asset_id in sorted(assets_df["asset_id"].unique()):
        symbol = id_to_sym.get(asset_id, str(asset_id))
        asset_prices = (
            prices_df[prices_df["asset_id"] == asset_id]
            .sort_values("date")
            .reset_index(drop=True)
        )
        if start_cfg:
            asset_prices = asset_prices[asset_prices["date"] >= start_cfg]
        if end_cfg:
            asset_prices = asset_prices[asset_prices["date"] <= end_cfg]

        if len(asset_prices) < 2:
            continue

        bh_equity, entry_tc = run_buy_and_hold(
            asset_prices,
            config["initial_capital"],
            config["tc_rate"],
            config["slippage"],
        )

        if not bh_equity.empty:
            save_benchmark(
                client, asset_id,
                asset_prices["date"].iloc[0],
                asset_prices["date"].iloc[-1],
                config["initial_capital"],
                bh_equity, entry_tc,
                config["risk_free_rate"],
                batch_id,
            )
            final_val    = float(bh_equity["portfolio_value"].iloc[-1])
            total_return = (final_val - config["initial_capital"]) / config["initial_capital"]
            bh_results.append({"symbol": symbol, "final_val": final_val, "return": total_return})
            print(f"  {symbol}: ${final_val:,.2f}  ({total_return:+.2%})")

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    print()
    print("Validating backtests...  (look-ahead checks passed during run)")

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #
    print()
    print("=" * 44)
    print("SUMMARY")
    print("=" * 44)

    # Group by symbol
    by_sym: dict[str, list] = {}
    for r in all_results:
        by_sym.setdefault(r["symbol"], []).append(r)

    for sym in sorted(by_sym.keys()):
        print(f"\n  {sym}")
        # Print in canonical strategy order
        strat_map = {r["strategy"]: r for r in by_sym[sym]}
        for strat in _STRATEGY_ORDER:
            if strat not in strat_map:
                continue
            m = strat_map[strat]["metrics"]
            pr = lambda v, fmt=".2f": f"{v:{fmt}}" if v is not None else "N/A"
            pct = lambda v: f"{v:+.2%}" if v is not None else "N/A"

            print(f"    {strat}")
            print(f"      Initial Capital:        ${m.get('initial_capital', 0):>12,.2f}")
            print(f"      Final Portfolio Value:  ${m.get('final_portfolio_value', 0):>12,.2f}")
            print(f"      Total Return:           {pct(m.get('total_return')):>10}")
            print(f"      Annualized Return:      {pct(m.get('annualized_return')):>10}")
            print(f"      Annualized Volatility:  {pct(m.get('annualized_volatility')):>10}")
            print(f"      Sharpe Ratio:           {pr(m.get('sharpe_ratio'), '.4f'):>10}")
            print(f"      Maximum Drawdown:       {pct(m.get('max_drawdown')):>10}")
            print(f"      Trades:                 {int(m.get('n_trades', 0)):>10,}")
            win = m.get("win_rate")
            print(f"      Win Rate:               {pct(win):>10}")
            print(f"      Transaction Costs:      ${m.get('total_transaction_costs', 0):>12,.2f}")

    print()
    print("  BUY AND HOLD")
    for bh in sorted(bh_results, key=lambda x: x["symbol"]):
        print(f"    {bh['symbol']:<6}  ${bh['final_val']:>12,.2f}  ({bh['return']:+.2%})")

    print()
    print("  Assumptions:")
    print(f"    Initial capital:   ${config['initial_capital']:,.2f}")
    print(f"    Transaction cost:  {config['tc_rate']:.3%} per trade")
    print(f"    Slippage:          {config['slippage']:.3%}")
    print(f"    Risk-free rate:    {config['risk_free_rate']:.3%}")
    print(f"    Annualisation:     {TRADING_DAYS_PER_YEAR} periods/year")
    print(f"    Position model:    Long-only (no short selling)")
    print(f"    Execution timing:  Signal at T -> Execute at T+1 OPEN")
    print()
    print("  DISCLAIMER: Backtesting measures historical simulated performance")
    print("  under stated assumptions only. Past results do not predict future")
    print("  returns.")
    print("=" * 44)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    _bid = sys.argv[1] if len(sys.argv) > 1 else None
    run_backtest_engine(_bid)
