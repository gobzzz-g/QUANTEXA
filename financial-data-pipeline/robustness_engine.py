"""
Robustness & Market Regime Analysis Engine – Layer 5
======================================================
Reads existing Supabase data (Layers 1–4) and produces:

  Part 1  – Parameter robustness
            All parameter configurations for each strategy,
            default transaction cost, full backtest period.

  Part 2  – Transaction-cost sensitivity
            Default parameters per strategy, five TC rates (0 % – 0.5 %).

  Part 3  – Time-period robustness
            Default parameters, default TC, three historical sub-periods.

  Part 4  – Market regime classification
            Deterministic rule-based: BULL/BEAR (SMA50 vs SMA200) ×
            HIGH/LOW volatility (vol_20 vs expanding-median threshold).
            No look-ahead bias: threshold at t = median(vol_0 … vol_t).

  Part 5  – Strategy performance by regime
            Splits Layer 4 equity / trade data by the regime active on
            each date and computes per-regime performance metrics.

What this layer does NOT do
----------------------------
  - Machine learning or AI
  - Portfolio optimisation or QUBO
  - Live trading or data download
  - Frontend / dashboard

Look-ahead bias guarantee
--------------------------
  • All signals come from Layer 3 logic using causal rolling windows.
  • Execution follows Layer 4 rule: signal at T → execute at T+1 OPEN.
  • Regime volatility threshold is an expanding (past-only) median.

Run:
    python robustness_engine.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ---------------------------------------------------------------------------
# Import pure functions from Layer 3 and Layer 4 (no duplication of logic)
# ---------------------------------------------------------------------------
try:
    from strategy_engine import (
        generate_sma_crossover_signals,
        generate_ema_trend_signals,
        generate_momentum_signals,
        generate_mean_reversion_signals,
    )
    from backtest_engine import (
        run_strategy_backtest,
        calculate_performance_metrics,
        calculate_max_drawdown,
    )
except ImportError as exc:
    print(f"ERROR: Cannot import Layer 3/4 modules: {exc}")
    print("Ensure strategy_engine.py and backtest_engine.py are in the same directory.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# IPv4 patch (required on this machine)
# ---------------------------------------------------------------------------
import socket as _socket

_orig_gai = _socket.getaddrinfo


def _ipv4_first(h, p, f=0, t=0, pr=0, fl=0):
    r = _orig_gai(h, p, f, t, pr, fl)
    return sorted(r, key=lambda x: 0 if x[0] == _socket.AF_INET else 1)


_socket.getaddrinfo = _ipv4_first

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_SIZE = 1000
BATCH_SIZE = 300
TRADING_DAYS_PER_YEAR = 252

# Default strategy parameters (identical to Layer 3 / Layer 4 defaults)
DEFAULT_PARAMS: dict[str, dict] = {
    "SMA_CROSSOVER":  {"fast_window": 20, "slow_window": 50},
    "EMA_TREND":      {"fast_window": 20, "slow_window": 50},
    "MOMENTUM":       {"lookback": 20},
    "MEAN_REVERSION": {"window": 20, "threshold": 0.02},
}

# ---------------------------------------------------------------------------
# Parameter grids  (edit these to change the robustness sweep)
# ---------------------------------------------------------------------------
_SMA_FAST  = [10, 20, 30, 50]
_SMA_SLOW  = [30, 50, 75, 100, 150, 200]
_MOM_LB    = [5, 10, 20, 40, 60, 120]
_MR_WIN    = [10, 20, 30, 50]
_MR_THR    = [0.01, 0.02, 0.03, 0.05]

# Transaction-cost rates to sweep (0.00% → 0.50%)
TC_RATES: list[float] = [0.0, 0.0005, 0.001, 0.002, 0.005]

# Historical sub-periods for time-period robustness
ANALYSIS_PERIODS: list[dict] = [
    {"name": "2020_2022",    "start": date(2020, 1, 1),  "end": date(2022, 12, 31)},
    {"name": "2023_2024",    "start": date(2023, 1, 1),  "end": date(2024, 12, 31)},
    {"name": "2025_present", "start": date(2025, 1, 1),  "end": None},  # None = use all available
]

# Valid regime/state strings
VALID_REGIMES   = frozenset({"BULL_LOW_VOL", "BULL_HIGH_VOL", "BEAR_LOW_VOL", "BEAR_HIGH_VOL", "UNKNOWN"})
VALID_TRENDS    = frozenset({"BULL", "BEAR", "UNKNOWN"})
VALID_VOL_STATS = frozenset({"HIGH_VOLATILITY", "LOW_VOLATILITY", "UNKNOWN"})


# ---------------------------------------------------------------------------
# Config / Client helpers
# ---------------------------------------------------------------------------


def _require_env(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        print(f"ERROR: env var '{key}' is not set.")
        sys.exit(1)
    return v


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
        "start_date":      _parse_date_env("ROBUSTNESS_START_DATE"),
        "end_date":        _parse_date_env("ROBUSTNESS_END_DATE"),
    }


def _get_client(config: dict) -> Client:
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
    """Paginate with mandatory batch_id filter — prevents cross-batch mixing."""
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


def _paginate_eq(client: Client, table: str, select: str, **filters) -> list[dict]:
    """Paginate with equality filters."""
    rows: list[dict] = []
    start = 0
    while True:
        q = client.table(table).select(select)
        for col, val in filters.items():
            q = q.eq(col, val)
        result = q.range(start, start + PAGE_SIZE - 1).execute()
        if not result.data:
            break
        rows.extend(result.data)
        if len(result.data) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows


def _params_key(p: Any) -> str:
    if isinstance(p, dict):
        return json.dumps(p, sort_keys=True)
    return str(p)


def _batch_upsert(client: Client, table: str, records: list[dict], on_conflict: str) -> int:
    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i : i + BATCH_SIZE]
        client.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        total += len(chunk)
    return total


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_base_data(
    client: Client,
    batch_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load market_prices, asset_indicators, and assets from Supabase.
    market_prices and asset_indicators are scoped to batch_id.
    assets is a global table (no batch filter).
    """
    print("  Loading market prices...")
    price_rows = _paginate_batch(client, "market_prices", "asset_id, date, open, close", batch_id)
    if not price_rows:
        raise ValueError(f"market_prices is empty for batch_id={batch_id}. Run Layer 1 first.")

    print("  Loading asset indicators...")
    ind_rows = _paginate_batch(
        client, "asset_indicators",
        "asset_id, date, sma_50, sma_200, volatility_20",
        batch_id,
    )
    if not ind_rows:
        raise ValueError(f"asset_indicators is empty for batch_id={batch_id}. Run Layer 2 first.")

    print("  Loading assets...")
    asset_rows = _paginate(client, "assets", "id, symbol, asset_type")

    prices_df    = pd.DataFrame(price_rows)
    indicators_df = pd.DataFrame(ind_rows)
    assets_df     = pd.DataFrame(asset_rows).rename(columns={"id": "asset_id"})

    prices_df["date"]     = pd.to_datetime(prices_df["date"]).dt.date
    indicators_df["date"] = pd.to_datetime(indicators_df["date"]).dt.date

    for col in ["open", "close"]:
        prices_df[col] = pd.to_numeric(prices_df[col], errors="coerce")

    for col in ["sma_50", "sma_200", "volatility_20"]:
        indicators_df[col] = pd.to_numeric(indicators_df[col], errors="coerce")

    return prices_df, indicators_df, assets_df


def _load_layer4_results(client: Client, batch_id: str) -> list[dict]:
    """
    Load Layer 4 default backtest results (equity + trades) for regime attribution.
    Only loads runs with status='SUCCESS' for the current batch.
    """
    runs = _paginate_batch(
        client, "backtest_runs",
        "id, asset_id, strategy_name, parameters, status",
        batch_id,
    )
    successful = [r for r in runs if r.get("status") == "SUCCESS"]
    if not successful:
        return []

    layer4 = []
    for run in successful:
        run_id = run["id"]

        equity_rows = _paginate_eq(
            client, "backtest_equity",
            "date, portfolio_value, daily_return, position",
            backtest_run_id=run_id,
        )
        trade_rows = _paginate_eq(
            client, "backtest_trades",
            "entry_date, entry_transaction_cost, exit_transaction_cost, net_pnl, status",
            backtest_run_id=run_id,
        )

        if not equity_rows:
            continue

        equity_df = pd.DataFrame(equity_rows)
        equity_df["date"]            = pd.to_datetime(equity_df["date"]).dt.date
        equity_df["portfolio_value"] = pd.to_numeric(equity_df["portfolio_value"], errors="coerce")
        equity_df["daily_return"]    = pd.to_numeric(equity_df["daily_return"], errors="coerce")

        trades = []
        for t in trade_rows:
            td = dict(t)
            if td.get("entry_date"):
                try:
                    td["entry_date"] = pd.to_datetime(td["entry_date"]).date()
                except Exception:
                    td["entry_date"] = None
            # Remap DB column names → internal short keys used in regime performance
            td["entry_tc"] = float(td.pop("entry_transaction_cost") or 0)
            td["exit_tc"]  = float(td.pop("exit_transaction_cost")  or 0)
            if td.get("net_pnl") is not None:
                td["net_pnl"] = float(td["net_pnl"])
            trades.append(td)

        params = run.get("parameters", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}

        layer4.append({
            "run_id":        run_id,
            "asset_id":      run["asset_id"],
            "strategy_name": run["strategy_name"],
            "parameters":    params,
            "equity_df":     equity_df,
            "trades":        trades,
        })

    return layer4


# ---------------------------------------------------------------------------
# Parameter grid generation
# ---------------------------------------------------------------------------


def generate_parameter_configurations() -> dict[str, list[dict]]:
    """
    Return all (valid) parameter configurations for each strategy.

    SMA / EMA:    only fast < slow combinations
    Momentum:     each lookback value
    Mean Reversion: each (window, threshold) pair
    """
    configs: dict[str, list[dict]] = {
        "SMA_CROSSOVER":  [],
        "EMA_TREND":      [],
        "MOMENTUM":       [],
        "MEAN_REVERSION": [],
    }

    for fast in _SMA_FAST:
        for slow in _SMA_SLOW:
            if fast < slow:
                configs["SMA_CROSSOVER"].append({"fast_window": fast, "slow_window": slow})
                configs["EMA_TREND"].append({"fast_window": fast, "slow_window": slow})

    for lb in _MOM_LB:
        configs["MOMENTUM"].append({"lookback": lb})

    for w in _MR_WIN:
        for t in _MR_THR:
            configs["MEAN_REVERSION"].append({"window": w, "threshold": t})

    return configs


# ---------------------------------------------------------------------------
# Signal generation helper (wraps Layer 3 functions)
# ---------------------------------------------------------------------------


def _prepare_indicator_df(
    prices_df: pd.DataFrame,
    strategy: str,
    params: dict,
) -> pd.DataFrame:
    """
    Build a DataFrame ready for Layer 3 signal functions.

    Computes required SMA/EMA windows on the fly from close prices
    (sorted by asset_id then date, grouped by asset_id).
    """
    df = prices_df.copy().sort_values(["asset_id", "date"]).reset_index(drop=True)

    # Columns required by _build_signal_df in strategy_engine.py
    if "symbol" not in df.columns:
        df["symbol"] = df["asset_id"].astype(str)
    if "asset_type" not in df.columns:
        df["asset_type"] = "UNKNOWN"

    df["daily_return"] = df.groupby("asset_id")["close"].pct_change()

    for col in ["volatility_20", "volatility_60", "volatility_252", "sma_200", "ema_200"]:
        if col not in df.columns:
            df[col] = float("nan")

    # Compute only the windows needed by this strategy / params
    needed_sma: set[int] = set()
    needed_ema: set[int] = set()

    if strategy == "SMA_CROSSOVER":
        needed_sma.update([params["fast_window"], params["slow_window"]])
    elif strategy == "EMA_TREND":
        needed_ema.update([params["fast_window"], params["slow_window"]])
    elif strategy == "MEAN_REVERSION":
        needed_sma.add(params["window"])
    # MOMENTUM only uses "close" via pct_change – no extra columns

    for w in needed_sma:
        col = f"sma_{w}"
        if col not in df.columns:
            df[col] = df.groupby("asset_id")["close"].transform(
                lambda s, w=w: s.rolling(w, min_periods=w).mean()
            )

    for w in needed_ema:
        col = f"ema_{w}"
        if col not in df.columns:
            df[col] = df.groupby("asset_id")["close"].transform(
                lambda s, w=w: s.ewm(span=w, adjust=False).mean()
            )

    return df


def _generate_signals(
    indicator_df: pd.DataFrame,
    strategy: str,
    params: dict,
) -> pd.DataFrame:
    """Call the appropriate Layer 3 signal function."""
    if strategy == "SMA_CROSSOVER":
        return generate_sma_crossover_signals(indicator_df, params["fast_window"], params["slow_window"])
    if strategy == "EMA_TREND":
        return generate_ema_trend_signals(indicator_df, params["fast_window"], params["slow_window"])
    if strategy == "MOMENTUM":
        return generate_momentum_signals(indicator_df, params["lookback"])
    if strategy == "MEAN_REVERSION":
        return generate_mean_reversion_signals(indicator_df, params["window"], params["threshold"])
    raise ValueError(f"Unknown strategy: {strategy}")


# ---------------------------------------------------------------------------
# Single backtest executor (pure – no Supabase)
# ---------------------------------------------------------------------------


def _run_single_backtest(
    asset_prices: pd.DataFrame,
    signals_df: pd.DataFrame,
    initial_capital: float,
    tc_rate: float,
    slippage: float,
    risk_free_rate: float,
) -> dict | None:
    """
    Merge prices + signals, run backtest, return metrics dict.
    Returns None if the data is insufficient.
    """
    data_df = asset_prices[["date", "open", "close"]].merge(
        signals_df[["date", "signal"]], on="date", how="left"
    ).sort_values("date").reset_index(drop=True)

    if len(data_df) < 2:
        return None

    equity_df, trades = run_strategy_backtest(data_df, initial_capital, tc_rate, slippage)

    if equity_df.empty:
        return None

    closed = [t for t in trades if t["status"] == "CLOSED"]
    return calculate_performance_metrics(equity_df, closed, initial_capital, risk_free_rate)


def _build_result_record(
    asset_id: str,
    strategy: str,
    params: dict,
    test_type: str,
    test_value: dict,
    start_date: date,
    end_date: date,
    initial_capital: float,
    metrics: dict | None,
) -> dict:
    """Construct a robustness_results row dict."""
    m = metrics or {}
    return {
        "asset_id":              asset_id,
        "strategy_name":         strategy,
        "parameters":            params,
        "test_type":             test_type,
        "test_value":            test_value,
        "start_date":            str(start_date),
        "end_date":              str(end_date),
        "initial_capital":       initial_capital,
        "final_portfolio_value": m.get("final_portfolio_value"),
        "total_return":          m.get("total_return"),
        "annualized_return":     m.get("annualized_return"),
        "annualized_volatility": m.get("annualized_volatility"),
        "sharpe_ratio":          m.get("sharpe_ratio"),
        "max_drawdown":          m.get("max_drawdown"),
        "trades":                m.get("n_trades"),
        "win_rate":              m.get("win_rate"),
        "transaction_costs":     m.get("total_transaction_costs"),
    }


# ---------------------------------------------------------------------------
# Part 1 – Parameter robustness
# ---------------------------------------------------------------------------


def run_parameter_robustness(
    prices_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    param_configs: dict[str, list[dict]],
    config: dict,
) -> list[dict]:
    """
    For every (strategy, parameter_config) combination, run a backtest
    with the default transaction cost and the full available period.

    Reuses Layer 3 signal functions and Layer 4 backtesting functions.
    Does NOT modify any Layer 1–4 data.
    """
    results: list[dict] = []
    ic      = config["initial_capital"]
    tc      = config["tc_rate"]
    slip    = config["slippage"]
    rfr     = config["risk_free_rate"]
    sd      = config.get("start_date")
    ed      = config.get("end_date")

    for strategy, configs in param_configs.items():
        for params in configs:
            ind_df  = _prepare_indicator_df(prices_df, strategy, params)
            sigs_df = _generate_signals(ind_df, strategy, params)

            for _, asset_row in assets_df.iterrows():
                aid = asset_row["asset_id"]

                ap = prices_df[prices_df["asset_id"] == aid].sort_values("date")
                if sd: ap = ap[ap["date"] >= sd]
                if ed: ap = ap[ap["date"] <= ed]
                if len(ap) < 2:
                    continue

                as_ = sigs_df[sigs_df["asset_id"] == aid].copy()
                if sd: as_ = as_[as_["date"] >= sd]
                if ed: as_ = as_[as_["date"] <= ed]

                m = _run_single_backtest(ap, as_, ic, tc, slip, rfr)

                results.append(_build_result_record(
                    aid, strategy, params,
                    "PARAMETER", params,
                    ap["date"].iloc[0], ap["date"].iloc[-1],
                    ic, m,
                ))

    return results


# ---------------------------------------------------------------------------
# Part 2 – Transaction-cost sensitivity
# ---------------------------------------------------------------------------


def run_transaction_cost_robustness(
    prices_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    config: dict,
) -> list[dict]:
    """
    For each strategy's DEFAULT parameter configuration, test every TC rate.

    test_type  = TRANSACTION_COST
    test_value = {"transaction_cost": <rate>}
    """
    results: list[dict] = []
    ic   = config["initial_capital"]
    slip = config["slippage"]
    rfr  = config["risk_free_rate"]
    sd   = config.get("start_date")
    ed   = config.get("end_date")

    for strategy, params in DEFAULT_PARAMS.items():
        ind_df  = _prepare_indicator_df(prices_df, strategy, params)
        sigs_df = _generate_signals(ind_df, strategy, params)

        for tc_rate in TC_RATES:
            for _, asset_row in assets_df.iterrows():
                aid = asset_row["asset_id"]

                ap = prices_df[prices_df["asset_id"] == aid].sort_values("date")
                if sd: ap = ap[ap["date"] >= sd]
                if ed: ap = ap[ap["date"] <= ed]
                if len(ap) < 2:
                    continue

                as_ = sigs_df[sigs_df["asset_id"] == aid].copy()
                if sd: as_ = as_[as_["date"] >= sd]
                if ed: as_ = as_[as_["date"] <= ed]

                m = _run_single_backtest(ap, as_, ic, tc_rate, slip, rfr)

                results.append(_build_result_record(
                    aid, strategy, params,
                    "TRANSACTION_COST", {"transaction_cost": tc_rate},
                    ap["date"].iloc[0], ap["date"].iloc[-1],
                    ic, m,
                ))

    return results


# ---------------------------------------------------------------------------
# Part 3 – Time-period robustness
# ---------------------------------------------------------------------------


def generate_time_periods(max_date: date) -> list[dict]:
    """
    Return ANALYSIS_PERIODS with None end-dates resolved to max_date.
    Drops periods where the resolved start >= resolved end.
    """
    periods = []
    for p in ANALYSIS_PERIODS:
        end = p["end"] if p["end"] is not None else max_date
        if end <= p["start"]:
            continue
        periods.append({"name": p["name"], "start": p["start"], "end": end})
    return periods


def run_time_period_robustness(
    prices_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    config: dict,
) -> list[dict]:
    """
    For each strategy's DEFAULT parameters, run a backtest in each
    historical sub-period independently.

    test_type  = TIME_PERIOD
    test_value = {"period_name": "<name>"}
    """
    results: list[dict] = []
    ic   = config["initial_capital"]
    tc   = config["tc_rate"]
    slip = config["slippage"]
    rfr  = config["risk_free_rate"]

    max_date = prices_df["date"].max()
    periods  = generate_time_periods(max_date)

    for period in periods:
        psd, ped, pname = period["start"], period["end"], period["name"]

        for strategy, params in DEFAULT_PARAMS.items():
            ind_df  = _prepare_indicator_df(prices_df, strategy, params)
            sigs_df = _generate_signals(ind_df, strategy, params)

            for _, asset_row in assets_df.iterrows():
                aid = asset_row["asset_id"]

                ap = (
                    prices_df[prices_df["asset_id"] == aid]
                    .sort_values("date")
                )
                ap = ap[(ap["date"] >= psd) & (ap["date"] <= ped)]
                if len(ap) < 2:
                    continue

                as_ = sigs_df[
                    (sigs_df["asset_id"] == aid)
                    & (sigs_df["date"] >= psd)
                    & (sigs_df["date"] <= ped)
                ].copy()

                m = _run_single_backtest(ap, as_, ic, tc, slip, rfr)

                results.append(_build_result_record(
                    aid, strategy, params,
                    "TIME_PERIOD", {"period_name": pname},
                    ap["date"].iloc[0], ap["date"].iloc[-1],
                    ic, m,
                ))

    return results


# ---------------------------------------------------------------------------
# Part 4 – Market regime classification
# ---------------------------------------------------------------------------


def calculate_expanding_volatility_threshold(vol_series: pd.Series) -> pd.Series:
    """
    Return the causal (expanding) median of volatility.

    At each time t, the threshold = median(vol_0, vol_1, …, vol_t).
    Future observations are NEVER used.

    Parameters
    ----------
    vol_series : pd.Series of rolling volatility values (ordered past→present)

    Returns
    -------
    pd.Series of the same length with causal threshold values.
    NaN where fewer than min_periods observations exist.
    """
    return vol_series.expanding(min_periods=1).median()


def classify_market_regimes(indicators_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign a market regime to every (asset_id, date) observation.

    Trend rule (uses Layer 2 SMA50 and SMA200):
        BULL   : sma_50 > sma_200
        BEAR   : sma_50 < sma_200
        UNKNOWN: either is NaN, or sma_50 == sma_200

    Volatility rule (expanding-median threshold – causal):
        HIGH_VOLATILITY : vol_20 >= threshold_t
        LOW_VOLATILITY  : vol_20 <  threshold_t
        UNKNOWN         : vol_20 or threshold is NaN

    Combined regime:
        BULL_LOW_VOL | BULL_HIGH_VOL | BEAR_LOW_VOL | BEAR_HIGH_VOL | UNKNOWN

    No look-ahead bias:
        threshold_t = median(vol_20[0 … t])
        Only information available at or before date t is used.
    """
    required = {"asset_id", "date", "sma_50", "sma_200", "volatility_20"}
    missing  = required - set(indicators_df.columns)
    if missing:
        raise ValueError(f"classify_market_regimes: missing columns {missing}")

    df = indicators_df[list(required)].copy()
    df = df.sort_values(["asset_id", "date"]).reset_index(drop=True)

    # ── Trend state ───────────────────────────────────────────────────────
    avail = df["sma_50"].notna() & df["sma_200"].notna()
    df["trend_state"] = "UNKNOWN"
    df.loc[avail & (df["sma_50"] > df["sma_200"]), "trend_state"] = "BULL"
    df.loc[avail & (df["sma_50"] < df["sma_200"]), "trend_state"] = "BEAR"
    # SMA50 == SMA200 → UNKNOWN (leaves existing 'UNKNOWN' unchanged)

    # Store SMA50/SMA200 ratio for auditability (None when unavailable)
    df["trend_value"] = np.where(
        avail & (df["sma_200"] != 0),
        df["sma_50"] / df["sma_200"],
        float("nan"),
    )

    # ── Volatility state (expanding-median threshold per asset) ───────────
    df["volatility_threshold"] = df.groupby("asset_id")["volatility_20"].transform(
        calculate_expanding_volatility_threshold
    )

    vol_avail = df["volatility_20"].notna() & df["volatility_threshold"].notna()
    df["volatility_state"] = "UNKNOWN"
    df.loc[vol_avail & (df["volatility_20"] >= df["volatility_threshold"]), "volatility_state"] = "HIGH_VOLATILITY"
    df.loc[vol_avail & (df["volatility_20"] <  df["volatility_threshold"]), "volatility_state"] = "LOW_VOLATILITY"

    # ── Combined regime ───────────────────────────────────────────────────
    def _combine(trend: str, vol: str) -> str:
        if trend == "UNKNOWN" or vol == "UNKNOWN":
            return "UNKNOWN"
        t = "BULL" if trend == "BULL" else "BEAR"
        v = "LOW_VOL" if vol == "LOW_VOLATILITY" else "HIGH_VOL"
        return f"{t}_{v}"

    df["regime"] = df.apply(
        lambda row: _combine(row["trend_state"], row["volatility_state"]), axis=1
    )

    return df[[
        "asset_id", "date",
        "trend_state", "volatility_state", "regime",
        "trend_value", "volatility_20", "volatility_threshold",
    ]].rename(columns={"volatility_20": "volatility_value"})


# ---------------------------------------------------------------------------
# Part 4 – Validation
# ---------------------------------------------------------------------------


def validate_regimes(regimes_df: pd.DataFrame) -> None:
    """
    Validate regime DataFrame before saving.

    Checks
    ------
    1.  All regime values are in VALID_REGIMES.
    2.  All trend_state values are in VALID_TRENDS.
    3.  All volatility_state values are in VALID_VOL_STATS.
    4.  No duplicate (asset_id, date) rows.
    5.  Dates sorted within each asset.
    """
    invalid_regime = set(regimes_df["regime"].unique()) - VALID_REGIMES
    if invalid_regime:
        raise ValueError(f"Invalid regime values: {invalid_regime}")

    invalid_trend = set(regimes_df["trend_state"].unique()) - VALID_TRENDS
    if invalid_trend:
        raise ValueError(f"Invalid trend_state values: {invalid_trend}")

    invalid_vol = set(regimes_df["volatility_state"].unique()) - VALID_VOL_STATS
    if invalid_vol:
        raise ValueError(f"Invalid volatility_state values: {invalid_vol}")

    dup = regimes_df.duplicated(subset=["asset_id", "date"], keep=False)
    if dup.any():
        raise ValueError(
            f"Found {dup.sum()} duplicate (asset_id, date) rows in regime data."
        )

    for aid, grp in regimes_df.groupby("asset_id", sort=False):
        dates = grp["date"].tolist()
        if dates != sorted(dates):
            raise ValueError(f"Dates not sorted for asset_id={aid}.")


# ---------------------------------------------------------------------------
# Part 5 – Strategy performance by regime
# ---------------------------------------------------------------------------


def calculate_regime_performance(
    layer4_results: list[dict],
    regimes_df: pd.DataFrame,
    risk_free_rate: float,
) -> list[dict]:
    """
    Split each Layer 4 equity curve by market regime and compute
    performance metrics for each (asset, strategy, params, regime) group.

    Trade attribution: trades are attributed to the regime active on
    their entry_date. This avoids using future regime information.

    Returns a list of strategy_regime_performance records.
    """
    all_perf: list[dict] = []

    for run in layer4_results:
        asset_id   = run["asset_id"]
        equity_df  = run["equity_df"]
        trades     = run["trades"]
        strategy   = run["strategy_name"]
        params     = run["parameters"]

        asset_regimes = (
            regimes_df[regimes_df["asset_id"] == asset_id][["date", "regime"]]
            .copy()
        )
        if asset_regimes.empty:
            continue

        merged = equity_df.merge(asset_regimes, on="date", how="left")
        merged["regime"] = merged["regime"].fillna("UNKNOWN")
        merged = merged.sort_values("date")

        for regime, grp in merged.groupby("regime"):
            grp   = grp.sort_values("date")
            n_days = len(grp)
            if n_days < 2:
                continue

            pv          = grp["portfolio_value"].tolist()
            dates       = grp["date"].tolist()
            daily_rets  = grp["daily_return"].dropna()

            total_ret = (pv[-1] / pv[0] - 1.0) if pv[0] > 0 else None
            ann_ret   = (
                (1.0 + total_ret) ** (TRADING_DAYS_PER_YEAR / n_days) - 1.0
                if (total_ret is not None and total_ret > -1.0) else None
            )
            ann_vol = (
                float(daily_rets.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
                if len(daily_rets) > 1 else None
            )
            sharpe = (
                (ann_ret - risk_free_rate) / ann_vol
                if (ann_vol and ann_vol > 0 and ann_ret is not None) else None
            )
            dd = calculate_max_drawdown(pv, dates)

            regime_date_set = set(dates)
            regime_trades   = [t for t in trades if t.get("entry_date") in regime_date_set]
            closed_rt       = [t for t in regime_trades if t.get("status") == "CLOSED"]
            winning  = [t for t in closed_rt if t.get("net_pnl") is not None and float(t["net_pnl"]) > 0]
            losing   = [t for t in closed_rt if t.get("net_pnl") is not None and float(t["net_pnl"]) < 0]
            win_rate = len(winning) / len(closed_rt) if closed_rt else None
            tc_total = sum(
                (float(t.get("entry_tc") or 0) + float(t.get("exit_tc") or 0))
                for t in regime_trades
            )

            all_perf.append({
                "asset_id":             asset_id,
                "strategy_name":        strategy,
                "parameters":           params,
                "regime":               regime,
                "start_date":           str(dates[0]),
                "end_date":             str(dates[-1]),
                "trading_days":         n_days,
                "trades":               len(regime_trades),
                "total_return":         total_ret,
                "annualized_return":    ann_ret,
                "annualized_volatility": ann_vol,
                "sharpe_ratio":         sharpe,
                "max_drawdown":         dd["max_drawdown"],
                "winning_trades":       len(winning),
                "losing_trades":        len(losing),
                "win_rate":             win_rate,
                "transaction_costs":    tc_total,
            })

    return all_perf


# ---------------------------------------------------------------------------
# Robustness statistics (descriptive only – no ranking)
# ---------------------------------------------------------------------------


def calculate_robustness_statistics(
    robustness_records: list[dict],
) -> dict[tuple[str, str], dict]:
    """
    Compute descriptive statistics across PARAMETER test results per
    (asset_id, strategy_name).

    Returns
    -------
    dict of (asset_id, strategy_name) → stats dict

    The statistics describe the distribution of outcomes – they do NOT
    declare a winner or rank parameter configurations.
    """
    param_recs = [r for r in robustness_records if r.get("test_type") == "PARAMETER"]

    groups: dict[tuple, list] = defaultdict(list)
    for r in param_recs:
        groups[(r["asset_id"], r["strategy_name"])].append(r)

    stats: dict[tuple[str, str], dict] = {}
    for (aid, strat), recs in groups.items():
        returns   = [r["total_return"]  for r in recs if r.get("total_return")  is not None]
        sharpes   = [r["sharpe_ratio"]  for r in recs if r.get("sharpe_ratio")  is not None]
        drawdowns = [r["max_drawdown"]  for r in recs if r.get("max_drawdown")  is not None]

        stats[(aid, strat)] = {
            "n_configs":           len(recs),
            "mean_return":         float(np.mean(returns))   if returns else None,
            "median_return":       float(np.median(returns)) if returns else None,
            "std_return":          float(np.std(returns))    if len(returns) > 1 else None,
            "min_return":          float(np.min(returns))    if returns else None,
            "max_return":          float(np.max(returns))    if returns else None,
            "mean_sharpe":         float(np.mean(sharpes))   if sharpes else None,
            "median_sharpe":       float(np.median(sharpes)) if sharpes else None,
            "std_sharpe":          float(np.std(sharpes))    if len(sharpes) > 1 else None,
            "mean_max_drawdown":   float(np.mean(drawdowns)) if drawdowns else None,
            "median_max_drawdown": float(np.median(drawdowns)) if drawdowns else None,
            "n_profitable":        sum(1 for r in returns if r > 0),
            "n_losing":            sum(1 for r in returns if r < 0),
        }

    return stats


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------


def save_market_regimes(client: Client, regimes_df: pd.DataFrame, batch_id: str) -> int:
    """Upsert market regime rows with batch_id (idempotent)."""
    records = []
    for _, row in regimes_df.iterrows():
        def _f(v):
            return None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)

        records.append({
            "batch_id":            batch_id,
            "asset_id":            str(row["asset_id"]),
            "date":                str(row["date"]),
            "trend_state":         str(row["trend_state"]),
            "volatility_state":    str(row["volatility_state"]),
            "regime":              str(row["regime"]),
            "trend_value":         _f(row.get("trend_value")),
            "volatility_value":    _f(row.get("volatility_value")),
            "volatility_threshold": _f(row.get("volatility_threshold")),
        })

    return _batch_upsert(client, "market_regimes", records, "batch_id,asset_id,date")


def save_robustness_results(client: Client, records: list[dict], batch_id: str) -> int:
    """Upsert robustness result rows with batch_id (idempotent)."""
    def _f(v):
        if v is None:
            return None
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return None
        return v

    formatted = []
    for r in records:
        formatted.append({
            "batch_id":              batch_id,
            "asset_id":              str(r["asset_id"]),
            "strategy_name":         r["strategy_name"],
            "parameters":            r["parameters"],
            "test_type":             r["test_type"],
            "test_value":            r["test_value"],
            "start_date":            str(r["start_date"]),
            "end_date":              str(r["end_date"]),
            "initial_capital":       _f(r.get("initial_capital")),
            "final_portfolio_value": _f(r.get("final_portfolio_value")),
            "total_return":          _f(r.get("total_return")),
            "annualized_return":     _f(r.get("annualized_return")),
            "annualized_volatility": _f(r.get("annualized_volatility")),
            "sharpe_ratio":          _f(r.get("sharpe_ratio")),
            "max_drawdown":          _f(r.get("max_drawdown")),
            "trades":                r.get("trades"),
            "win_rate":              _f(r.get("win_rate")),
            "transaction_costs":     _f(r.get("transaction_costs")),
        })

    return _batch_upsert(
        client, "robustness_results", formatted,
        "batch_id,asset_id,strategy_name,parameters,test_type,test_value,start_date,end_date",
    )


def save_regime_performance(client: Client, records: list[dict], batch_id: str) -> int:
    """Upsert strategy_regime_performance rows with batch_id (idempotent)."""
    def _f(v):
        if v is None:
            return None
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return None
        return v

    formatted = []
    for r in records:
        formatted.append({
            "batch_id":             batch_id,
            "asset_id":             str(r["asset_id"]),
            "strategy_name":        r["strategy_name"],
            "parameters":           r["parameters"],
            "regime":               r["regime"],
            "start_date":           str(r["start_date"]),
            "end_date":             str(r["end_date"]),
            "trading_days":         r.get("trading_days"),
            "trades":               r.get("trades"),
            "total_return":         _f(r.get("total_return")),
            "annualized_return":    _f(r.get("annualized_return")),
            "annualized_volatility": _f(r.get("annualized_volatility")),
            "sharpe_ratio":         _f(r.get("sharpe_ratio")),
            "max_drawdown":         _f(r.get("max_drawdown")),
            "winning_trades":       r.get("winning_trades"),
            "losing_trades":        r.get("losing_trades"),
            "win_rate":             _f(r.get("win_rate")),
            "transaction_costs":    _f(r.get("transaction_costs")),
        })

    return _batch_upsert(
        client, "strategy_regime_performance", formatted,
        "batch_id,asset_id,strategy_name,parameters,regime,start_date,end_date",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_robustness_engine(batch_id: str | None = None) -> None:
    """
    Execute the full robustness and regime analysis pipeline (batch-aware).

    Flow
    ----
    load data (scoped to batch_id)
      → generate parameter configurations
      → Part 1: parameter robustness
      → Part 2: TC sensitivity
      → Part 3: time-period robustness
      → Part 4: regime classification + validation
      → Part 5: regime performance (using Layer 4 equity for same batch)
      → descriptive statistics (printed, not ranked)
      → save all results to Supabase (with batch_id)
      → print summary
    """
    config = _get_config()
    client = _get_client(config)

    if batch_id is None:
        batch_id = input("Enter batch_id: ").strip()

    print("=" * 48)
    print("ROBUSTNESS & REGIME ENGINE")
    print("=" * 48)
    print()

    # ── Load data ──────────────────────────────────────────────────────────
    print("Loading data...")
    prices_df, indicators_df, assets_df = load_base_data(client, batch_id)
    n_assets = assets_df["asset_id"].nunique()
    print(f"  {len(prices_df):,} price rows,  {len(indicators_df):,} indicator rows,  {n_assets} assets.")
    print()

    id_to_sym = dict(zip(assets_df["asset_id"], assets_df["symbol"]))

    # ── Generate parameter configs ─────────────────────────────────────────
    print("Generating parameter configurations...")
    param_configs = generate_parameter_configurations()
    total_configs = sum(len(v) for v in param_configs.values())
    for strat, confs in param_configs.items():
        print(f"  {strat}: {len(confs)} configurations")
    print(f"  Total: {total_configs} configurations × {n_assets} assets")
    print()

    # ── Part 1: Parameter robustness ───────────────────────────────────────
    print("Running parameter robustness...")
    param_results = run_parameter_robustness(prices_df, assets_df, param_configs, config)
    print(f"  {len(param_results)} results generated.")
    print()

    # ── Part 2: TC sensitivity ─────────────────────────────────────────────
    print("Running transaction-cost sensitivity...")
    tc_results = run_transaction_cost_robustness(prices_df, assets_df, config)
    print(f"  {len(tc_results)} results generated ({len(TC_RATES)} TC rates × {len(DEFAULT_PARAMS)} strategies × {n_assets} assets).")
    print()

    # ── Part 3: Time-period robustness ─────────────────────────────────────
    print("Running time-period robustness...")
    period_results = run_time_period_robustness(prices_df, assets_df, config)
    max_date = prices_df["date"].max()
    periods  = generate_time_periods(max_date)
    print(f"  {len(period_results)} results generated ({len(periods)} periods × {len(DEFAULT_PARAMS)} strategies × {n_assets} assets).")
    print()

    all_robustness = param_results + tc_results + period_results

    # ── Part 4: Regime classification ──────────────────────────────────────
    print("Classifying market regimes...")
    regimes_df = classify_market_regimes(indicators_df)
    print(f"  {len(regimes_df):,} regime observations.")
    regime_counts = regimes_df["regime"].value_counts().to_dict()
    for regime, cnt in sorted(regime_counts.items()):
        pct = cnt / len(regimes_df) * 100
        print(f"    {regime:<20}: {cnt:>5} days ({pct:.1f}%)")
    print()

    print("Validating regimes...")
    validate_regimes(regimes_df)
    print("  All regime validation checks passed.")
    print()

    # ── Part 5: Regime performance ─────────────────────────────────────────
    print("Calculating regime performance...")
    print("  Loading Layer 4 backtest equity and trades...")
    layer4_results = _load_layer4_results(client, batch_id)
    print(f"  Loaded {len(layer4_results)} successful Layer 4 backtest run(s).")

    regime_perf = calculate_regime_performance(
        layer4_results, regimes_df, config["risk_free_rate"]
    )
    print(f"  {len(regime_perf)} regime-performance records computed.")
    print()

    # ── Robustness statistics (descriptive – no ranking) ───────────────────
    print("Calculating robustness statistics...")
    stats = calculate_robustness_statistics(all_robustness)
    print(f"  Statistics computed for {len(stats)} (asset, strategy) groups.")
    print()

    # ── Validation ─────────────────────────────────────────────────────────
    print("Validating results...")
    tc_vals = [r.get("transaction_costs") for r in all_robustness if r.get("transaction_costs") is not None]
    if any(v < 0 for v in tc_vals):
        raise ValueError("Negative transaction costs found in robustness results.")
    print("  All validation checks passed.")
    print()

    # ── Save results ───────────────────────────────────────────────────────
    print("Saving results...")

    print("  Saving market regimes...")
    n_reg = save_market_regimes(client, regimes_df, batch_id)
    print(f"    {n_reg} rows upserted to market_regimes.")

    print("  Saving robustness results...")
    n_rob = save_robustness_results(client, all_robustness, batch_id)
    print(f"    {n_rob} rows upserted to robustness_results.")

    print("  Saving regime performance...")
    n_rp = save_regime_performance(client, regime_perf, batch_id)
    print(f"    {n_rp} rows upserted to strategy_regime_performance.")
    print()

    # ── Summary ────────────────────────────────────────────────────────────
    print("=" * 48)
    print("SUMMARY")
    print("=" * 48)
    print()
    print(f"  Assets processed          : {n_assets}")
    print(f"  Strategies processed      : {len(DEFAULT_PARAMS)}")
    print(f"  Parameter configs tested  : {total_configs}")
    print(f"  TC scenarios tested       : {len(TC_RATES)}")
    print(f"  Time periods tested       : {len(periods)}")
    print(f"  Regime observations       : {len(regimes_df):,}")
    print(f"  Regime categories detected: {len(regime_counts)}")
    print(f"  Robustness records created: {len(all_robustness)}")
    print(f"  Regime perf. records      : {len(regime_perf)}")
    print()

    # Regime distribution per asset
    print("  Regime distribution by asset:")
    for aid in sorted(assets_df["asset_id"].unique()):
        sym = id_to_sym.get(aid, aid[:8])
        asset_reg = regimes_df[regimes_df["asset_id"] == aid]["regime"].value_counts()
        total = len(regimes_df[regimes_df["asset_id"] == aid])
        print(f"    {sym}")
        for reg in sorted(VALID_REGIMES):
            cnt = asset_reg.get(reg, 0)
            pct = cnt / total * 100 if total > 0 else 0
            print(f"      {reg:<20}: {cnt:>4} days ({pct:4.1f}%)")
    print()

    # Parameter robustness descriptive stats (no ranking)
    print("  Parameter robustness statistics (descriptive):")
    print(f"  {'Asset':<8} {'Strategy':<16} {'N':>4}  "
          f"{'Med.Ret':>9}  {'Std.Ret':>9}  {'Med.Sharpe':>11}  "
          f"{'Profitable':>11}  {'Losing':>7}")
    print("  " + "-" * 85)
    for (aid, strat), s in sorted(stats.items(), key=lambda x: (id_to_sym.get(x[0][0], ""), x[0][1])):
        sym = id_to_sym.get(aid, aid[:8])
        mr  = f"{s['median_return']:+.2%}"  if s['median_return']  is not None else "N/A"
        sr  = f"{s['std_return']:.2%}"      if s['std_return']     is not None else "N/A"
        ms  = f"{s['median_sharpe']:+.3f}"  if s['median_sharpe']  is not None else "N/A"
        print(f"  {sym:<8} {strat:<16} {s['n_configs']:>4}  "
              f"{mr:>9}  {sr:>9}  {ms:>11}  "
              f"{s['n_profitable']:>11}  {s['n_losing']:>7}")
    print()
    print("  NOTE: Statistics are descriptive only.")
    print("        No configurations are ranked, scored, or declared 'best'.")
    print()
    print("  DISCLAIMER: All analysis is based on historical simulated data.")
    print("  Robustness across parameters does not guarantee future stability.")
    print("=" * 48)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    _bid = sys.argv[1] if len(sys.argv) > 1 else None
    run_robustness_engine(_bid)
