"""
Quantitative Analysis Engine – Layer 2
========================================
Reads validated historical market data from Supabase ``market_prices``
and computes quantitative financial features for each asset.

Run:
    python quant_engine.py

Environment variables (see .env.example):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    RISK_FREE_RATE   (optional, default 0.0)

Documented assumptions
----------------------
Annualisation
    All return and volatility figures use 252 trading periods per year
    for every asset, including BTC-USD which trades 24/7.  This is the
    standard convention in quantitative finance research.  It will be
    revisited in a later layer when asset-specific calendars are modelled.

Risk-free rate
    Defaults to 0.0 (configurable via RISK_FREE_RATE).  The resulting
    Sharpe ratio is therefore an excess-return-free measure of return per
    unit of risk.  Replace with the prevailing T-bill rate when needed.

Look-ahead bias
    All rolling calculations use only data available at time T:
    - SMA uses rolling(window, min_periods=window).mean()
    - EMA uses ewm(span, adjust=False).mean()  (causal by design)
    - Volatility uses rolling(window, min_periods=window).std()
    No future observations are ever used.

Missing data
    Missing prices are never forward-filled.  NaN observations propagate
    correctly through rolling windows.

Trading calendars
    NVDA  – NYSE equity trading days only
    BTC   – every calendar day (24/7)
    GC=F  – CME Globex futures calendar
    Pairwise correlations are computed on the INTERSECTION of trading
    dates for each asset pair.  No artificial observations are created.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from itertools import combinations
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ---------------------------------------------------------------------------
# Network: force IPv4 for environments where IPv6 is unavailable
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

#: Trading periods per year applied to ALL assets (including BTC 24/7).
ANNUALIZATION_FACTOR: int = 252

#: Rolling windows for volatility (trading days)
VOLATILITY_WINDOWS: list[int] = [20, 60, 252]

#: SMA and EMA spans (trading days)
MA_WINDOWS: list[int] = [20, 50, 200]

#: Rolling windows for pairwise correlation (trading days)
CORRELATION_WINDOWS: list[int] = [30, 60, 90]

#: Supabase REST row limit per request; used for pagination and batch upserts
PAGE_SIZE: int = 1000
BATCH_SIZE: int = 500

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env(key: str) -> str:
    """Return env var value or abort with a clear message."""
    value = os.getenv(key, "").strip()
    if not value:
        print(f"ERROR: Environment variable '{key}' is not set or empty.")
        sys.exit(1)
    return value


def _get_config() -> dict[str, Any]:
    return {
        "supabase_url": _require_env("SUPABASE_URL"),
        "supabase_key": _require_env("SUPABASE_SERVICE_ROLE_KEY"),
        "risk_free_rate": float(os.getenv("RISK_FREE_RATE", "0.0")),
    }


def _get_client(config: dict[str, Any]) -> Client:
    return create_client(config["supabase_url"], config["supabase_key"])


def _safe_float(value: Any) -> float | None:
    """Return float or None; converts NaN and Inf to None."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _paginate(client: Client, table: str, select: str) -> list[dict]:
    """
    Fetch ALL rows from a Supabase table.

    The Supabase REST API returns at most 1,000 rows per request.
    This function pages through all results transparently.
    """
    rows: list[dict] = []
    start = 0
    while True:
        result = (
            client.table(table)
            .select(select)
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
    """
    Fetch ALL rows for a specific batch_id from a Supabase table.
    Every SELECT on a batch-specific table MUST be scoped to batch_id.
    """
    rows: list[dict] = []
    start = 0
    while True:
        result = (
            client.table(table)
            .select(select)
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


def _upsert_batched(
    client: Client,
    table: str,
    records: list[dict],
    on_conflict: str,
) -> int:
    """Upsert records in BATCH_SIZE chunks and return total rows upserted."""
    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i : i + BATCH_SIZE]
        client.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        total += len(chunk)
    return total


# ---------------------------------------------------------------------------
# Step 1 – load_market_data
# ---------------------------------------------------------------------------


def load_market_data(client: Client, batch_id: str) -> pd.DataFrame:
    """
    Load market_prices for a specific batch_id, joined with assets metadata.

    Every SELECT is scoped to batch_id to prevent cross-batch data mixing.

    Returns a DataFrame sorted by (asset_id, date) with columns:
        asset_id, symbol, asset_type, date,
        open, high, low, close, volume

    Raises
    ------
    ValueError
        If no rows found for this batch (Layer 1 has not been run).
    """
    price_rows = _paginate_batch(
        client,
        "market_prices",
        "asset_id, date, open, high, low, close, volume",
        batch_id,
    )
    if not price_rows:
        raise ValueError(
            f"market_prices is empty for batch_id={batch_id}. "
            "Run Layer 1 first."
        )

    asset_rows = _paginate(client, "assets", "id, symbol, asset_type, name")
    if not asset_rows:
        raise ValueError("assets table is empty.")

    prices_df = pd.DataFrame(price_rows)
    assets_df = pd.DataFrame(asset_rows).rename(columns={"id": "asset_id"})

    df = prices_df.merge(assets_df, on="asset_id", how="inner")

    # Ensure correct types
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(["asset_id", "date"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Step 2 – calculate_returns
# ---------------------------------------------------------------------------


def calculate_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-asset daily return: (close_t / close_{t-1}) - 1.

    Calculation is performed within each asset group so that the first
    observation per asset is always NaN (no prior price available).
    This prevents cross-asset contamination of the return series.
    """
    df = df.copy()
    df["daily_return"] = df.groupby("asset_id", sort=False)["close"].pct_change()
    return df


# ---------------------------------------------------------------------------
# Step 3 – calculate_moving_averages
# ---------------------------------------------------------------------------


def calculate_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append SMA and EMA columns for windows 20, 50, and 200.

    SMA
        ``rolling(window, min_periods=window).mean()``
        Values are NaN until exactly ``window`` observations are available.
        This guarantees no look-ahead bias.

    EMA
        ``ewm(span=window, adjust=False).mean()``
        Defined from the first observation; early values are less stable
        but no future data is used (causal filter by construction).
    """
    df = df.copy()

    for window in MA_WINDOWS:
        # SMA
        df[f"sma_{window}"] = df.groupby("asset_id", sort=False)["close"].transform(
            lambda s, w=window: s.rolling(window=w, min_periods=w).mean()
        )
        # EMA
        df[f"ema_{window}"] = df.groupby("asset_id", sort=False)["close"].transform(
            lambda s, w=window: s.ewm(span=w, adjust=False).mean()
        )

    return df


# ---------------------------------------------------------------------------
# Step 4 – calculate_volatility
# ---------------------------------------------------------------------------


def calculate_volatility(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append rolling standard-deviation-of-returns columns.

    Windows: 20, 60, 252 observations.
    Values are NaN until exactly ``window`` returns are available.

    Note: these are RAW rolling standard deviations (not annualised).
    Annualised volatility is computed separately in calculate_asset_statistics.
    """
    df = df.copy()

    for window in VOLATILITY_WINDOWS:
        df[f"volatility_{window}"] = df.groupby(
            "asset_id", sort=False
        )["daily_return"].transform(
            lambda s, w=window: s.rolling(window=w, min_periods=w).std()
        )

    return df


# ---------------------------------------------------------------------------
# Step 5 – calculate_max_drawdown  (helper, called from step 6)
# ---------------------------------------------------------------------------


def calculate_max_drawdown(
    close: np.ndarray,
    dates: np.ndarray,
) -> dict[str, Any]:
    """
    Calculate maximum drawdown from a numpy array of close prices.

    Drawdown at time t:
        drawdown_t = (close_t / running_peak_t) - 1

    where running_peak_t = max(close_0, …, close_t).

    Maximum drawdown is the minimum (most negative) drawdown value.

    Parameters
    ----------
    close : 1-D float array of close prices (no NaN allowed)
    dates : 1-D array of corresponding date objects

    Returns
    -------
    dict with keys:
        max_drawdown               float (<= 0)
        max_drawdown_start_date    date of the peak before trough
        max_drawdown_trough_date   date of deepest loss
        max_drawdown_recovery_date date of first recovery to peak (or None)
    """
    _empty = {
        "max_drawdown": None,
        "max_drawdown_start_date": None,
        "max_drawdown_trough_date": None,
        "max_drawdown_recovery_date": None,
    }
    if len(close) < 2:
        return _empty

    running_peak = np.maximum.accumulate(close)
    drawdown = (close / running_peak) - 1.0

    # Trough: position of worst drawdown
    trough_pos = int(np.argmin(drawdown))
    max_dd = float(drawdown[trough_pos])

    # Peak before trough: position of maximum price in [0, trough_pos]
    peak_pos = int(np.argmax(close[: trough_pos + 1]))

    start_date = dates[peak_pos]
    trough_date = dates[trough_pos]

    # Recovery: first date AFTER trough where price >= peak price
    peak_price = running_peak[trough_pos]
    post_trough = close[trough_pos + 1 :]   # strictly after the trough
    recovered = np.where(post_trough >= peak_price)[0]
    recovery_date = dates[trough_pos + 1 + recovered[0]] if len(recovered) > 0 else None

    return {
        "max_drawdown": max_dd,
        "max_drawdown_start_date": start_date,
        "max_drawdown_trough_date": trough_date,
        "max_drawdown_recovery_date": recovery_date,
    }


# ---------------------------------------------------------------------------
# Step 6 – calculate_asset_statistics
# ---------------------------------------------------------------------------


def calculate_asset_statistics(
    df: pd.DataFrame,
    risk_free_rate: float,
) -> list[dict[str, Any]]:
    """
    Compute per-asset summary statistics over the full available history.

    Formulas
    --------
    Total return
        (last_close / first_close) - 1

    Annualised return  (geometric, 252-day convention)
        (1 + total_return)^(252 / n_trading_days) - 1
        where n_trading_days = count of non-NaN return observations.

    Annualised volatility
        std(daily_returns) × sqrt(252)

    Sharpe ratio
        (annualised_return - RISK_FREE_RATE) / annualised_volatility
        Returns None when annualised_volatility is 0 or unavailable.

    Maximum drawdown
        See calculate_max_drawdown().
    """
    stats: list[dict[str, Any]] = []

    for asset_id, group in df.groupby("asset_id", sort=True):
        group = group.sort_values("date").reset_index(drop=True)

        close = group["close"].dropna()
        returns = group["daily_return"].dropna()

        if len(close) < 2 or len(returns) < 1:
            continue

        symbol = group["symbol"].iloc[0]
        start_date = str(group["date"].iloc[0])
        end_date = str(group["date"].iloc[-1])

        # Total return
        total_return = float((close.iloc[-1] / close.iloc[0]) - 1)

        # Annualised return using geometric compounding
        n_trading_days = len(returns)
        annualized_return = float(
            (1.0 + total_return) ** (ANNUALIZATION_FACTOR / n_trading_days) - 1.0
        )

        # Annualised volatility
        daily_std = float(returns.std()) if len(returns) > 1 else None
        annualized_vol = (
            float(daily_std * sqrt(ANNUALIZATION_FACTOR)) if daily_std is not None else None
        )

        # Sharpe ratio
        sharpe = None
        if (
            annualized_vol is not None
            and annualized_vol > 0
            and annualized_return is not None
        ):
            sharpe = float((annualized_return - risk_free_rate) / annualized_vol)

        # Maximum drawdown (use close prices aligned to their dates)
        close_vals = group["close"].dropna().values
        date_vals = group.loc[group["close"].notna(), "date"].values
        dd_result = calculate_max_drawdown(close_vals, date_vals)

        stats.append(
            {
                "asset_id": asset_id,
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "total_return": total_return,
                "annualized_return": annualized_return,
                "annualized_volatility": annualized_vol,
                "sharpe_ratio": sharpe,
                "max_drawdown": dd_result["max_drawdown"],
                "max_drawdown_start_date": (
                    str(dd_result["max_drawdown_start_date"])
                    if dd_result["max_drawdown_start_date"] is not None
                    else None
                ),
                "max_drawdown_trough_date": (
                    str(dd_result["max_drawdown_trough_date"])
                    if dd_result["max_drawdown_trough_date"] is not None
                    else None
                ),
                "max_drawdown_recovery_date": (
                    str(dd_result["max_drawdown_recovery_date"])
                    if dd_result["max_drawdown_recovery_date"] is not None
                    else None
                ),
            }
        )

    return stats


# ---------------------------------------------------------------------------
# Step 7 – calculate_correlations
# ---------------------------------------------------------------------------


def calculate_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate pairwise rolling return correlations for all asset pairs.

    For each pair of assets:
        1. Dates are restricted to those where BOTH assets have a return
           (respects different trading calendars without inventing data).
        2. Rolling Pearson correlation is computed with
           ``rolling(window, min_periods=window).corr()``.
        3. NaN values (insufficient observations) are dropped.

    Pair ordering
        Always stored as (smaller_uuid, larger_uuid) to satisfy the
        ``ordered_asset_pair`` CHECK constraint in Supabase.

    Returns
    -------
    DataFrame with columns:
        asset_1_id, asset_2_id, date, window, correlation
    """
    # Wide-format returns: index=date, columns=asset_id
    returns_wide = df.pivot_table(
        index="date",
        columns="asset_id",
        values="daily_return",
    )

    asset_ids = sorted(returns_wide.columns.tolist())  # sort for determinism
    pairs = list(combinations(asset_ids, 2))           # (a,b) with a < b always

    records: list[dict[str, Any]] = []

    for window in CORRELATION_WINDOWS:
        for a1_id, a2_id in pairs:
            # Intersect to common trading dates only
            pair_returns = returns_wide[[a1_id, a2_id]].dropna()

            if len(pair_returns) < window:
                continue  # Not enough common observations for this window

            rolling_corr: pd.Series = (
                pair_returns[a1_id]
                .rolling(window=window, min_periods=window)
                .corr(pair_returns[a2_id])
            )

            for dt, corr_val in rolling_corr.items():
                if pd.isna(corr_val):
                    continue
                records.append(
                    {
                        "asset_1_id": a1_id,   # guaranteed < a2_id (see sorted + combinations)
                        "asset_2_id": a2_id,
                        "date": str(dt),
                        "window_days": window,
                        "correlation": float(corr_val),
                    }
                )

    if not records:
        return pd.DataFrame(
            columns=["asset_1_id", "asset_2_id", "date", "window_days", "correlation"]
        )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Step 8 – validate_calculations
# ---------------------------------------------------------------------------


def validate_calculations(
    indicators_df: pd.DataFrame,
    stats_list: list[dict[str, Any]],
    corr_df: pd.DataFrame,
) -> None:
    """
    Validate all calculated results before writing to Supabase.

    Raises ValueError with a descriptive message on the first failure.

    Checks
    ------
    1.  Dates are sorted within each asset group.
    2.  No duplicate (asset_id, date) records.
    3.  Non-NaN daily returns are finite.
    4.  Non-NaN SMA values are finite.
    5.  Non-NaN EMA values are finite.
    6.  Non-NaN volatility values are non-negative.
    7.  Non-NaN correlation values are in [-1.0, +1.0].
    8.  Sharpe ratio is finite when annualised_volatility > 0.
    9.  Maximum drawdown is <= 0.
    10. No look-ahead bias (structural guarantee: min_periods == window).
    """
    # 1. Dates sorted within each asset
    for asset_id, grp in indicators_df.groupby("asset_id", sort=False):
        dates = grp["date"].tolist()
        if dates != sorted(dates):
            raise ValueError(
                f"Dates are not sorted for asset_id={asset_id}. "
                "This indicates a bug in load_market_data or calculate_returns."
            )

    # 2. No duplicate (asset_id, date) records
    dup_mask = indicators_df.duplicated(subset=["asset_id", "date"], keep=False)
    if dup_mask.any():
        n_dups = dup_mask.sum()
        raise ValueError(
            f"Found {n_dups} duplicate (asset_id, date) row(s) in indicators."
        )

    # 3. Daily returns are finite when not NaN
    ret_vals = indicators_df["daily_return"].dropna()
    bad_ret = ret_vals[~np.isfinite(ret_vals)]
    if not bad_ret.empty:
        raise ValueError(
            f"Non-finite daily_return values found at indices: {bad_ret.index.tolist()}"
        )

    # 4. SMA values finite when present
    for col in [f"sma_{w}" for w in MA_WINDOWS]:
        if col not in indicators_df.columns:
            continue
        vals = indicators_df[col].dropna()
        if not np.isfinite(vals).all():
            raise ValueError(f"Non-finite values found in column '{col}'.")

    # 5. EMA values finite when present
    for col in [f"ema_{w}" for w in MA_WINDOWS]:
        if col not in indicators_df.columns:
            continue
        vals = indicators_df[col].dropna()
        if not np.isfinite(vals).all():
            raise ValueError(f"Non-finite values found in column '{col}'.")

    # 6. Volatility non-negative
    for col in [f"volatility_{w}" for w in VOLATILITY_WINDOWS]:
        if col not in indicators_df.columns:
            continue
        vals = indicators_df[col].dropna()
        if (vals < 0).any():
            raise ValueError(f"Negative volatility found in column '{col}'.")

    # 7. Correlations in [-1, +1]
    if not corr_df.empty and "correlation" in corr_df.columns:
        c = corr_df["correlation"].dropna()
        out_of_range = c[(c < -1.0 - 1e-9) | (c > 1.0 + 1e-9)]
        if not out_of_range.empty:
            raise ValueError(
                f"Correlation values outside [-1, 1]: {out_of_range.values}"
            )

    # 8. Sharpe ratio finite when vol > 0
    for stat in stats_list:
        vol = stat.get("annualized_volatility")
        sharpe = stat.get("sharpe_ratio")
        if vol is not None and vol > 0 and sharpe is not None:
            if not np.isfinite(sharpe):
                raise ValueError(
                    f"Non-finite Sharpe ratio for {stat.get('symbol')}: {sharpe}"
                )

    # 9. Maximum drawdown <= 0
    for stat in stats_list:
        dd = stat.get("max_drawdown")
        if dd is not None and dd > 1e-9:
            raise ValueError(
                f"Max drawdown > 0 for {stat.get('symbol')}: {dd:.6f}. "
                "Check the drawdown calculation."
            )

    # 10. Look-ahead bias is a structural guarantee:
    #     - SMA uses rolling(window, min_periods=window) → NaN until window full
    #     - EMA uses ewm(adjust=False) → causal, uses only current + past
    #     - Volatility uses rolling(window, min_periods=window).std()
    #     No runtime check needed beyond verifying NaN presence for short series.
    for _, grp in indicators_df.groupby("asset_id", sort=False):
        n = len(grp)
        for window in MA_WINDOWS:
            col = f"sma_{window}"
            if col not in grp.columns or n < window:
                continue
            first_valid = grp[col].first_valid_index()
            if first_valid is None:
                continue
            pos = grp.index.get_loc(first_valid)
            if pos < window - 1:
                raise ValueError(
                    f"Look-ahead bias detected: {col} has a non-NaN value before "
                    f"{window} observations are available (position {pos})."
                )


# ---------------------------------------------------------------------------
# Step 9 – save_indicators
# ---------------------------------------------------------------------------


def save_indicators(client: Client, df: pd.DataFrame, batch_id: str) -> int:
    """Upsert per-asset per-date indicators to ``asset_indicators`` with batch_id."""
    indicator_cols = [
        "asset_id", "date",
        "daily_return",
        "sma_20", "sma_50", "sma_200",
        "ema_20", "ema_50", "ema_200",
        "volatility_20", "volatility_60", "volatility_252",
    ]

    records: list[dict[str, Any]] = []
    for _, row in df[indicator_cols].iterrows():
        records.append(
            {
                "batch_id":        batch_id,
                "asset_id":        row["asset_id"],
                "date":            str(row["date"]),
                "daily_return":    _safe_float(row["daily_return"]),
                "sma_20":          _safe_float(row["sma_20"]),
                "sma_50":          _safe_float(row["sma_50"]),
                "sma_200":         _safe_float(row["sma_200"]),
                "ema_20":          _safe_float(row["ema_20"]),
                "ema_50":          _safe_float(row["ema_50"]),
                "ema_200":         _safe_float(row["ema_200"]),
                "volatility_20":   _safe_float(row["volatility_20"]),
                "volatility_60":   _safe_float(row["volatility_60"]),
                "volatility_252":  _safe_float(row["volatility_252"]),
            }
        )

    return _upsert_batched(client, "asset_indicators", records, "batch_id,asset_id,date")


# ---------------------------------------------------------------------------
# Step 10 – save_statistics
# ---------------------------------------------------------------------------


def save_statistics(
    client: Client,
    stats_list: list[dict[str, Any]],
    batch_id: str,
) -> int:
    """Upsert per-asset summary statistics to ``asset_statistics`` with batch_id."""
    records: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for stat in stats_list:
        records.append(
            {
                "batch_id":               batch_id,
                "asset_id":               stat["asset_id"],
                "start_date":             stat["start_date"],
                "end_date":               stat["end_date"],
                "total_return":           _safe_float(stat["total_return"]),
                "annualized_return":      _safe_float(stat["annualized_return"]),
                "annualized_volatility":  _safe_float(stat["annualized_volatility"]),
                "sharpe_ratio":           _safe_float(stat["sharpe_ratio"]),
                "max_drawdown":           _safe_float(stat["max_drawdown"]),
                "max_drawdown_start_date":    stat.get("max_drawdown_start_date"),
                "max_drawdown_trough_date":   stat.get("max_drawdown_trough_date"),
                "max_drawdown_recovery_date": stat.get("max_drawdown_recovery_date"),
                "updated_at": now,
            }
        )

    return _upsert_batched(
        client,
        "asset_statistics",
        records,
        "batch_id,asset_id,start_date,end_date",
    )


# ---------------------------------------------------------------------------
# Step 11 – save_correlations
# ---------------------------------------------------------------------------


def save_correlations(client: Client, corr_df: pd.DataFrame, batch_id: str) -> int:
    """Upsert rolling pairwise correlations to ``asset_correlations`` with batch_id."""
    if corr_df.empty:
        return 0

    records: list[dict[str, Any]] = []
    for _, row in corr_df.iterrows():
        records.append(
            {
                "batch_id":    batch_id,
                "asset_1_id":  row["asset_1_id"],
                "asset_2_id":  row["asset_2_id"],
                "date":        str(row["date"]),
                "window_days": int(row["window_days"]),
                "correlation": _safe_float(row["correlation"]),
            }
        )

    return _upsert_batched(
        client,
        "asset_correlations",
        records,
        "batch_id,asset_1_id,asset_2_id,date,window_days",
    )


# ---------------------------------------------------------------------------
# Orchestrator – run_quant_engine
# ---------------------------------------------------------------------------


def run_quant_engine(batch_id: str | None = None) -> None:
    """
    Execute the full quantitative analysis pipeline.

    Flow
    ----
    load_market_data
      → calculate_returns
      → calculate_moving_averages
      → calculate_volatility
      → calculate_asset_statistics  (+ calculate_max_drawdown internally)
      → calculate_correlations
      → validate_calculations
      → save_indicators
      → save_statistics
      → save_correlations
    """
    config = _get_config()
    client = _get_client(config)
    risk_free_rate = config["risk_free_rate"]

    if batch_id is None:
        batch_id = input("Enter batch_id: ").strip()

    print("=" * 40)
    print("QUANTITATIVE ANALYSIS ENGINE")
    print("=" * 40)
    print(f"  Batch: {batch_id}")
    print()

    # ------------------------------------------------------------------
    print("Loading market data...")
    df = load_market_data(client, batch_id)
    n_assets = df["asset_id"].nunique()
    n_rows = len(df)
    print(f"  Loaded {n_rows:,} price rows across {n_assets} asset(s).")

    symbols = df.groupby("asset_id")["symbol"].first().to_dict()
    for aid, sym in symbols.items():
        n = (df["asset_id"] == aid).sum()
        date_min = df.loc[df["asset_id"] == aid, "date"].min()
        date_max = df.loc[df["asset_id"] == aid, "date"].max()
        print(f"  {sym}: {n:,} rows  [{date_min} -> {date_max}]")
    print()

    # ------------------------------------------------------------------
    print("Calculating returns...")
    df = calculate_returns(df)

    print("Calculating SMA...")
    print("Calculating EMA...")
    df = calculate_moving_averages(df)

    print("Calculating volatility...")
    df = calculate_volatility(df)

    # ------------------------------------------------------------------
    print("Calculating asset statistics...")
    stats_list = calculate_asset_statistics(df, risk_free_rate)

    print("Calculating maximum drawdown...")  # (called inside calc_asset_statistics)

    # ------------------------------------------------------------------
    print("Calculating correlations...")
    corr_df = calculate_correlations(df)

    # Print full-period correlation matrix
    returns_wide = df.pivot_table(
        index="date", columns="symbol", values="daily_return"
    )
    full_corr = returns_wide.corr()
    print("\n  Full-period return correlation matrix (pairwise complete obs):")
    print(full_corr.to_string(float_format=lambda x: f"{x:.4f}"))
    print()

    # ------------------------------------------------------------------
    print("Validating calculations...")
    validate_calculations(df, stats_list, corr_df)
    print("  All validation checks passed.")
    print()

    # ------------------------------------------------------------------
    print("Saving indicators...")
    n_ind = save_indicators(client, df, batch_id)
    print(f"  {n_ind:,} rows upserted to asset_indicators.")

    print("Saving statistics...")
    n_stat = save_statistics(client, stats_list, batch_id)
    print(f"  {n_stat} row(s) upserted to asset_statistics.")

    print("Saving correlations...")
    n_corr = save_correlations(client, corr_df, batch_id)
    print(f"  {n_corr:,} rows upserted to asset_correlations.")
    print()

    # ------------------------------------------------------------------
    print("=" * 40)
    print("SUMMARY")
    print("=" * 40)
    print()

    for stat in stats_list:
        sym = stat["symbol"]
        ret = stat["annualized_return"]
        vol = stat["annualized_volatility"]
        sr = stat["sharpe_ratio"]
        mdd = stat["max_drawdown"]

        print(f"  {sym}")
        print(
            f"    Annualised return:     {ret * 100:+.2f}%"
            if ret is not None else "    Annualised return:     N/A"
        )
        print(
            f"    Annualised volatility: {vol * 100:.2f}%"
            if vol is not None else "    Annualised volatility: N/A"
        )
        print(
            f"    Sharpe ratio:          {sr:.4f}"
            if sr is not None else "    Sharpe ratio:          N/A"
        )
        print(
            f"    Maximum drawdown:      {mdd * 100:.2f}%"
            if mdd is not None else "    Maximum drawdown:      N/A"
        )
        print(
            f"    DD trough date:        {stat['max_drawdown_trough_date']}"
        )
        print()

    print("  Quantitative analysis completed.")
    print(f"  Risk-free rate used: {risk_free_rate:.4f}")
    print(
        f"  Annualisation factor: {ANNUALIZATION_FACTOR} "
        "(applied uniformly to all assets including BTC)"
    )
    print("=" * 40)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    _bid = sys.argv[1] if len(sys.argv) > 1 else None
    run_quant_engine(_bid)
