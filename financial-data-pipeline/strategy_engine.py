"""
Strategy Engine – Layer 3
===========================
Reads quantitative indicators from Layer 2 (asset_indicators, market_prices)
and generates deterministic trading signals for four strategies.

Strategies implemented
----------------------
  SMA_CROSSOVER   SMA fast/slow crossover (default 20/50)
  EMA_TREND       EMA fast/slow crossover (default 20/50)
  MOMENTUM        Rolling momentum = close_t / close_{t-N} - 1 (default N=20)
  MEAN_REVERSION  Price deviation from SMA beyond a configurable band (default ±2%)

Signal convention
-----------------
     1  =  LONG            bullish signal
     0  =  FLAT            neutral / no directional edge
    -1  =  EXIT / SHORT    bearish signal

IMPORTANT – interpretation of -1:
    This layer does NOT decide whether -1 means exit-only or a short position.
    That decision belongs to the backtesting layer (Layer 4).

What this layer does NOT do
----------------------------
  - Execute trades or simulate positions
  - Calculate P&L, transaction costs, or slippage
  - Size positions or manage portfolio weights
  - Perform backtesting or optimisation

Missing indicator handling
--------------------------
    If a required indicator is NULL/NaN (e.g. SMA200 before 200 observations),
    no signal is generated for that (asset, date, strategy) combination.
    The corresponding row is simply absent from strategy_signals.

Look-ahead bias
---------------
    All indicators consumed by this layer were computed by Layer 2 using only
    data available at or before date T (rolling causal windows).  Momentum is
    calculated via pct_change(N), which uses close_{t-N} only.
    No future information is used.

Run:
    python strategy_engine.py

Environment variables (see .env.example):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    SMA_FAST, SMA_SLOW
    EMA_FAST, EMA_SLOW
    MOMENTUM_LOOKBACK
    MEAN_REVERSION_WINDOW, MEAN_REVERSION_THRESHOLD
"""

from __future__ import annotations

import json
import os
import sys
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

PAGE_SIZE: int = 1000
BATCH_SIZE: int = 500

VALID_STRATEGIES: frozenset[str] = frozenset(
    {"SMA_CROSSOVER", "EMA_TREND", "MOMENTUM", "MEAN_REVERSION"}
)

# Columns required in the loaded DataFrame
_INDICATOR_COLS = [
    "daily_return",
    "sma_20", "sma_50", "sma_200",
    "ema_20", "ema_50", "ema_200",
    "volatility_20", "volatility_60", "volatility_252",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        print(f"ERROR: Environment variable '{key}' is not set or empty.")
        sys.exit(1)
    return value


def _get_config() -> dict[str, Any]:
    """Load and validate all strategy configuration from environment."""
    return {
        "supabase_url": _require_env("SUPABASE_URL"),
        "supabase_key": _require_env("SUPABASE_SERVICE_ROLE_KEY"),
        # SMA Crossover
        "sma_fast": int(os.getenv("SMA_FAST", "20")),
        "sma_slow": int(os.getenv("SMA_SLOW", "50")),
        # EMA Trend
        "ema_fast": int(os.getenv("EMA_FAST", "20")),
        "ema_slow": int(os.getenv("EMA_SLOW", "50")),
        # Momentum
        "momentum_lookback": int(os.getenv("MOMENTUM_LOOKBACK", "20")),
        # Mean Reversion
        "mr_window":    int(os.getenv("MEAN_REVERSION_WINDOW", "20")),
        "mr_threshold": float(os.getenv("MEAN_REVERSION_THRESHOLD", "0.02")),
    }


def _get_client(config: dict[str, Any]) -> Client:
    return create_client(config["supabase_url"], config["supabase_key"])


def _paginate(client: Client, table: str, select: str) -> list[dict]:
    """Fetch ALL rows, transparently handling Supabase's 1 000-row page limit."""
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
    """Paginate with mandatory batch_id filter to prevent cross-batch mixing."""
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
    """Upsert in BATCH_SIZE chunks; return total rows sent."""
    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i : i + BATCH_SIZE]
        client.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        total += len(chunk)
    return total


def _make_signal_series(
    valid_mask: pd.Series,
    long_mask: pd.Series,
    short_mask: pd.Series,
) -> pd.Series:
    """
    Build an object-dtype signal Series.

    Returns
    -------
    Series with values 1, 0, -1 where valid_mask is True; None elsewhere.
    None signals are NOT persisted to the database — they represent dates
    where a required indicator was unavailable.
    """
    sig = pd.Series([None] * len(valid_mask), index=valid_mask.index, dtype=object)
    sig[valid_mask & long_mask]  = 1
    sig[valid_mask & short_mask] = -1
    # everything in valid_mask that is neither long nor short → 0
    flat_mask = valid_mask & ~long_mask & ~short_mask
    sig[flat_mask] = 0
    return sig


# ---------------------------------------------------------------------------
# Step 1 – load_strategy_data
# ---------------------------------------------------------------------------


def load_strategy_data(client: Client, batch_id: str) -> pd.DataFrame:
    """
    Load and join:
      - asset_indicators  (scoped to batch_id)
      - market_prices     (scoped to batch_id)
      - assets            (global table, no batch filter)

    The join between asset_indicators and market_prices is explicitly
    scoped to the same batch to prevent cross-batch contamination.
    """
    ind_select = (
        "asset_id, date, daily_return, "
        "sma_20, sma_50, sma_200, "
        "ema_20, ema_50, ema_200, "
        "volatility_20, volatility_60, volatility_252"
    )
    ind_rows = _paginate_batch(client, "asset_indicators", ind_select, batch_id)
    if not ind_rows:
        raise ValueError(
            f"asset_indicators is empty for batch_id={batch_id}. Run Layer 2 first."
        )

    price_rows = _paginate_batch(client, "market_prices", "asset_id, date, close", batch_id)
    if not price_rows:
        raise ValueError(
            f"market_prices is empty for batch_id={batch_id}. Run Layer 1 first."
        )

    asset_rows = _paginate(client, "assets", "id, symbol, asset_type")
    if not asset_rows:
        raise ValueError("assets table is empty.")

    ind_df    = pd.DataFrame(ind_rows)
    price_df  = pd.DataFrame(price_rows)
    assets_df = pd.DataFrame(asset_rows).rename(columns={"id": "asset_id"})

    # Type coercions
    for df_ in (ind_df, price_df):
        df_["date"] = pd.to_datetime(df_["date"]).dt.date

    for col in _INDICATOR_COLS:
        if col in ind_df.columns:
            ind_df[col] = pd.to_numeric(ind_df[col], errors="coerce")

    price_df["close"] = pd.to_numeric(price_df["close"], errors="coerce")

    # Join: indicators + close price — both already scoped to same batch_id
    df = ind_df.merge(price_df[["asset_id", "date", "close"]], on=["asset_id", "date"], how="left")

    # Join: + asset metadata (global)
    df = df.merge(assets_df, on="asset_id", how="left")

    df = df.sort_values(["asset_id", "date"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Step 2 – generate_sma_crossover_signals
# ---------------------------------------------------------------------------


def generate_sma_crossover_signals(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
) -> pd.DataFrame:
    """
    SMA Crossover Strategy.

    Rules
    -----
    LONG  (1):  sma_fast > sma_slow
    EXIT  (-1): sma_fast < sma_slow
    FLAT  (0):  sma_fast == sma_slow
    NULL  (None): either MA is unavailable (early dates before window fills)

    Parameters
    ----------
    fast : int  Fast SMA window. Must be pre-calculated by Layer 2.
    slow : int  Slow SMA window. Must be pre-calculated by Layer 2.
    """
    fast_col = f"sma_{fast}"
    slow_col = f"sma_{slow}"
    params: dict[str, Any] = {"fast_window": fast, "slow_window": slow}

    if fast_col not in df.columns or slow_col not in df.columns:
        # Window not pre-calculated by Layer 2 — all signals NULL
        return _build_signal_df(df, "SMA_CROSSOVER", params, pd.Series([None] * len(df), dtype=object))

    fast_vals = df[fast_col]
    slow_vals = df[slow_col]
    valid     = fast_vals.notna() & slow_vals.notna()

    sig = _make_signal_series(
        valid_mask  = valid,
        long_mask   = fast_vals > slow_vals,
        short_mask  = fast_vals < slow_vals,
    )
    return _build_signal_df(df, "SMA_CROSSOVER", params, sig)


# ---------------------------------------------------------------------------
# Step 3 – generate_ema_trend_signals
# ---------------------------------------------------------------------------


def generate_ema_trend_signals(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
) -> pd.DataFrame:
    """
    EMA Trend Strategy.

    Rules
    -----
    LONG  (1):  ema_fast > ema_slow
    EXIT  (-1): ema_fast < ema_slow
    FLAT  (0):  ema_fast == ema_slow
    NULL  (None): either EMA is unavailable

    Parameters
    ----------
    fast : int  Fast EMA span. Must be pre-calculated by Layer 2.
    slow : int  Slow EMA span. Must be pre-calculated by Layer 2.
    """
    fast_col = f"ema_{fast}"
    slow_col = f"ema_{slow}"
    params: dict[str, Any] = {"fast_window": fast, "slow_window": slow}

    if fast_col not in df.columns or slow_col not in df.columns:
        return _build_signal_df(df, "EMA_TREND", params, pd.Series([None] * len(df), dtype=object))

    fast_vals = df[fast_col]
    slow_vals = df[slow_col]
    valid     = fast_vals.notna() & slow_vals.notna()

    sig = _make_signal_series(
        valid_mask  = valid,
        long_mask   = fast_vals > slow_vals,
        short_mask  = fast_vals < slow_vals,
    )
    return _build_signal_df(df, "EMA_TREND", params, sig)


# ---------------------------------------------------------------------------
# Step 4 – generate_momentum_signals
# ---------------------------------------------------------------------------


def generate_momentum_signals(
    df: pd.DataFrame,
    lookback: int = 20,
) -> pd.DataFrame:
    """
    Momentum Strategy.

    Momentum = close_t / close_{t-lookback} - 1

    Calculated PER ASSET GROUP to prevent cross-asset contamination.

    Rules
    -----
    LONG  (1):  momentum > 0
    EXIT  (-1): momentum < 0
    FLAT  (0):  momentum == 0
    NULL  (None): fewer than ``lookback`` observations available,
                  or close price is missing

    Parameters
    ----------
    lookback : int  Number of periods to look back. Default 20.
    """
    params: dict[str, Any] = {"lookback": lookback}

    # pct_change(N) computed within each asset group — no cross-contamination
    momentum: pd.Series = df.groupby("asset_id", sort=False)["close"].transform(
        lambda s, n=lookback: s.pct_change(periods=n)
    )

    valid = momentum.notna() & df["close"].notna()

    sig = _make_signal_series(
        valid_mask  = valid,
        long_mask   = momentum > 0,
        short_mask  = momentum < 0,
    )
    return _build_signal_df(df, "MOMENTUM", params, sig)


# ---------------------------------------------------------------------------
# Step 5 – generate_mean_reversion_signals
# ---------------------------------------------------------------------------


def generate_mean_reversion_signals(
    df: pd.DataFrame,
    window: int   = 20,
    threshold: float = 0.02,
) -> pd.DataFrame:
    """
    Mean Reversion Strategy.

    distance_from_sma = (close - sma_N) / sma_N

    Rules
    -----
    LONG  (1):  close < sma_N * (1 - threshold)
                    → price significantly below average: potential upward reversion
    EXIT  (-1): close > sma_N * (1 + threshold)
                    → price significantly above average: potential downward reversion
    FLAT  (0):  price within the band
    NULL  (None): sma_N or close unavailable

    DISCLAIMER: This is a deterministic rule, not a price-reversion prediction.
    The backtesting layer decides whether the trade is profitable.

    Parameters
    ----------
    window    : int    SMA window to compare against. Default 20.
    threshold : float  Band width as fraction of SMA. Default 0.02 (2%).
    """
    sma_col = f"sma_{window}"
    params: dict[str, Any] = {"window": window, "threshold": threshold}

    if sma_col not in df.columns:
        return _build_signal_df(df, "MEAN_REVERSION", params, pd.Series([None] * len(df), dtype=object))

    sma_vals   = df[sma_col]
    close_vals = df["close"]
    valid      = sma_vals.notna() & close_vals.notna() & (sma_vals != 0)

    lower_band = sma_vals * (1.0 - threshold)
    upper_band = sma_vals * (1.0 + threshold)

    sig = _make_signal_series(
        valid_mask = valid,
        long_mask  = close_vals < lower_band,
        short_mask = close_vals > upper_band,
    )
    return _build_signal_df(df, "MEAN_REVERSION", params, sig)


# ---------------------------------------------------------------------------
# Internal: build output DataFrame
# ---------------------------------------------------------------------------


def _build_signal_df(
    source_df: pd.DataFrame,
    strategy_name: str,
    parameters: dict[str, Any],
    signal_series: pd.Series,
) -> pd.DataFrame:
    """
    Construct the standard signal output DataFrame.

    Columns: asset_id, date, strategy_name, parameters, signal
    """
    return pd.DataFrame(
        {
            "asset_id":      source_df["asset_id"].values,
            "date":          source_df["date"].values,
            "strategy_name": strategy_name,
            "parameters":    [parameters] * len(source_df),
            "signal":        signal_series.values,
        }
    )


# ---------------------------------------------------------------------------
# Step 6 – validate_signals
# ---------------------------------------------------------------------------


def validate_signals(all_signals: pd.DataFrame) -> None:
    """
    Validate all generated signals before persisting.

    Raises ValueError with a clear message on the first failure.

    Checks
    ------
    1.  Signal values are only -1, 0, 1, or None.
    2.  No duplicate (asset_id, date, strategy_name, parameters) rows.
    3.  Dates are sorted within each (asset_id, strategy_name) group.
    4.  No future data used (structural guarantee from Layer 2 + causal logic).
    5.  NULL signals only when required indicators are missing.
    6.  All strategy_name values are known.
    7.  All parameters are non-empty dicts.
    8.  Each asset is processed independently (no cross-asset rows).
    """
    # 1. Signal values
    non_null = all_signals["signal"].dropna()
    invalid_vals = non_null[~non_null.isin([-1, 0, 1])]
    if not invalid_vals.empty:
        raise ValueError(
            f"Invalid signal values found (must be -1, 0, or 1): {invalid_vals.unique()}"
        )

    # 2. No duplicates — use canonical JSON for JSONB comparison
    temp = all_signals.copy()
    temp["_pkey"] = temp["parameters"].apply(
        lambda p: json.dumps(p, sort_keys=True) if isinstance(p, dict) else str(p)
    )
    dup_mask = temp.duplicated(
        subset=["asset_id", "date", "strategy_name", "_pkey"], keep=False
    )
    if dup_mask.any():
        raise ValueError(
            f"Found {dup_mask.sum()} duplicate (asset_id, date, strategy_name, parameters) rows."
        )

    # 3. Dates sorted — group by (asset_id, strategy_name, canonical_parameters)
    #    Two configs of the same strategy are independent date series.
    if "_pkey" not in all_signals.columns:
        all_signals = all_signals.copy()
        all_signals["_pkey"] = all_signals["parameters"].apply(
            lambda p: json.dumps(p, sort_keys=True) if isinstance(p, dict) else str(p)
        )
        _pkey_added = True
    else:
        _pkey_added = False

    for (aid, strat, pkey), grp in all_signals.groupby(
        ["asset_id", "strategy_name", "_pkey"], sort=False
    ):
        dates = grp["date"].tolist()
        if dates != sorted(dates):
            raise ValueError(
                f"Dates not sorted for asset_id={aid}, strategy={strat}. "
                "Check load_strategy_data() sort order."
            )

    if _pkey_added:
        all_signals.drop(columns=["_pkey"], inplace=True)

    # 4. Look-ahead bias — structural guarantee:
    #    • SMA/EMA/vol from Layer 2 use causal rolling windows
    #    • Momentum uses pct_change(N) — only uses past N closes
    #    • Mean reversion compares close vs SMA — both are T-available

    # 5. NULL signals only when indicators missing — guaranteed by _make_signal_series:
    #    valid_mask is False whenever any required column is NaN → signal = None

    # 6. Valid strategy names
    unknown = set(all_signals["strategy_name"].unique()) - VALID_STRATEGIES
    if unknown:
        raise ValueError(f"Unknown strategy names: {unknown}")

    # 7. Parameters are non-empty dicts
    bad_params = all_signals[
        all_signals["parameters"].apply(
            lambda p: not isinstance(p, dict) or len(p) == 0
        )
    ]
    if not bad_params.empty:
        raise ValueError(
            f"Empty or non-dict parameters in {len(bad_params)} rows."
        )

    # 8. Assets processed independently — guaranteed by per-asset groupby in momentum
    #    and by using df's own columns (no cross-merges) in other strategies


# ---------------------------------------------------------------------------
# Step 7 – save_strategy_signals
# ---------------------------------------------------------------------------


def save_strategy_signals(client: Client, all_signals: pd.DataFrame, batch_id: str) -> int:
    """
    Upsert non-null signals to ``strategy_signals`` with batch_id.

    NULL signals (missing indicator rows) are filtered out before saving.
    Running this function multiple times for the same batch is idempotent.

    Returns
    -------
    int  Number of rows sent to Supabase.
    """
    saveable = all_signals[all_signals["signal"].notna()].copy()
    if saveable.empty:
        return 0

    records: list[dict] = []
    for _, row in saveable.iterrows():
        records.append(
            {
                "batch_id":      batch_id,
                "asset_id":      str(row["asset_id"]),
                "date":          str(row["date"]),
                "strategy_name": row["strategy_name"],
                "parameters":    row["parameters"],   # dict -> JSONB
                "signal":        int(row["signal"]),
            }
        )

    return _upsert_batched(
        client,
        "strategy_signals",
        records,
        "batch_id,asset_id,date,strategy_name",
    )


# ---------------------------------------------------------------------------
# Orchestrator – run_strategy_engine
# ---------------------------------------------------------------------------


def run_strategy_engine(batch_id: str | None = None) -> None:
    """
    Execute the full strategy signal generation pipeline.

    Flow
    ----
    load_strategy_data (batch-scoped)
      -> generate signals
      -> validate_signals
      -> save_strategy_signals (with batch_id)
    """
    config = _get_config()
    client = _get_client(config)

    if batch_id is None:
        batch_id = input("Enter batch_id: ").strip()

    print("=" * 40)
    print("STRATEGY ENGINE")
    print("=" * 40)
    print(f"  Batch: {batch_id}")
    print()

    # ----------------------------------------------------------------
    print("Loading strategy data...")
    df = load_strategy_data(client, batch_id)
    n_assets = df["asset_id"].nunique()
    n_rows = len(df)
    print(f"  Loaded {n_rows:,} rows for {n_assets} asset(s).")
    print()

    # ----------------------------------------------------------------
    print("Generating SMA crossover signals...")
    sma_sigs = generate_sma_crossover_signals(
        df, config["sma_fast"], config["sma_slow"]
    )

    print("Generating EMA trend signals...")
    ema_sigs = generate_ema_trend_signals(
        df, config["ema_fast"], config["ema_slow"]
    )

    print("Generating momentum signals...")
    mom_sigs = generate_momentum_signals(df, config["momentum_lookback"])

    print("Generating mean reversion signals...")
    mr_sigs = generate_mean_reversion_signals(
        df, config["mr_window"], config["mr_threshold"]
    )
    print()

    # ----------------------------------------------------------------
    all_signals = pd.concat(
        [sma_sigs, ema_sigs, mom_sigs, mr_sigs], ignore_index=True
    )

    print("Validating signals...")
    validate_signals(all_signals)
    print("  All validation checks passed.")
    print()

    # ----------------------------------------------------------------
    print("Saving strategy signals...")
    n_saved = save_strategy_signals(client, all_signals, batch_id)
    print(f"  {n_saved:,} signals upserted to strategy_signals.")
    print()

    # ----------------------------------------------------------------
    # Summary
    symbol_map: dict[str, str] = (
        df.drop_duplicates("asset_id")
        .set_index("asset_id")["symbol"]
        .to_dict()
    )
    all_signals["symbol"] = all_signals["asset_id"].map(symbol_map)

    print("=" * 40)
    print("SUMMARY")
    print("=" * 40)
    print()

    for sym in sorted(symbol_map.values()):
        sym_sigs = all_signals[all_signals["symbol"] == sym]
        print(f"  {sym}")

        for strat in ["SMA_CROSSOVER", "EMA_TREND", "MOMENTUM", "MEAN_REVERSION"]:
            strat_sigs = sym_sigs[sym_sigs["strategy_name"] == strat]
            long_c = int((strat_sigs["signal"] == 1).sum())
            flat_c = int((strat_sigs["signal"] == 0).sum())
            exit_c = int((strat_sigs["signal"] == -1).sum())
            null_c = int(strat_sigs["signal"].isna().sum())
            print(
                f"    {strat}"
                f"\n      LONG: {long_c:>5}  FLAT: {flat_c:>5}"
                f"  EXIT: {exit_c:>5}  NULL: {null_c:>5}"
            )
        print()

    print("  Strategy generation completed.")
    print(
        f"  Parameters used:"
        f"  SMA {config['sma_fast']}/{config['sma_slow']}"
        f"  |  EMA {config['ema_fast']}/{config['ema_slow']}"
        f"  |  MOM lookback={config['momentum_lookback']}"
        f"  |  MR window={config['mr_window']} threshold={config['mr_threshold']}"
    )
    print("=" * 40)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    _bid = sys.argv[1] if len(sys.argv) > 1 else None
    run_strategy_engine(_bid)
