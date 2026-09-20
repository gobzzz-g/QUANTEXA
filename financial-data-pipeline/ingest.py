"""
Financial Data Ingestion Pipeline – Layer 1 (Batch-Aware)
==========================================================
Supports two ingestion modes:

  1. CSV mode (batch pipeline)
     Called by run_pipeline.py with a user-provided CSV path and a
     pre-created batch_id.  No Yahoo Finance download occurs.

  2. Yahoo Finance mode (legacy / standalone)
     Invoked when running `python ingest.py` directly.
     Retains original behaviour for the LEGACY batch.

CSV format expected:
    date,asset[,asset_type],open,high,low,close,volume

Minimum required columns: date, asset, close
Preferred:                 date, asset, asset_type, open, high, low, close, volume

If asset_type column is absent the pipeline prompts the user for each
asset's type interactively.  Asset types are NEVER silently defaulted.

Environment variables (see .env.example):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    YAHOO_GOLD_TICKER        (legacy Yahoo mode only)
    YAHOO_BITCOIN_TICKER     (legacy Yahoo mode only)
    YAHOO_NVIDIA_TICKER      (legacy Yahoo mode only)
    START_DATE               (legacy Yahoo mode only)
    END_DATE                 (legacy Yahoo mode only)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

# ---------------------------------------------------------------------------
# Network: prefer IPv4 over IPv6
# ---------------------------------------------------------------------------

import socket as _socket

_orig_getaddrinfo = _socket.getaddrinfo


def _ipv4_first_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    results = _orig_getaddrinfo(host, port, family, type, proto, flags)
    return sorted(results, key=lambda r: 0 if r[0] == _socket.AF_INET else 1)


_socket.getaddrinfo = _ipv4_first_getaddrinfo

# ---------------------------------------------------------------------------
# Directory layout  (used by Yahoo Finance legacy mode only)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent
RAW_DIR = ROOT / "data" / "raw"
QUALITY_DIR = ROOT / "data" / "quality"

QUALITY_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
SOURCE_NAME = "Yahoo Finance"
SOURCE_CSV  = "CSV Upload"
BATCH_SIZE  = 500

VALID_ASSET_TYPES = {"EQUITY", "COMMODITY", "CRYPTOCURRENCY"}

# ---------------------------------------------------------------------------
# Asset catalogue (legacy Yahoo Finance mode only)
# ---------------------------------------------------------------------------

LEGACY_ASSETS: list[dict[str, str]] = [
    {
        "key": "gold",
        "symbol": "GOLD",
        "name": "Gold",
        "asset_type": "COMMODITY",
        "env_ticker": "YAHOO_GOLD_TICKER",
        "raw_path": str(RAW_DIR / "gold" / "gold_raw.csv"),
        "quality_path": str(QUALITY_DIR / "gold_quality.json"),
    },
    {
        "key": "bitcoin",
        "symbol": "BTC",
        "name": "Bitcoin",
        "asset_type": "CRYPTOCURRENCY",
        "env_ticker": "YAHOO_BITCOIN_TICKER",
        "raw_path": str(RAW_DIR / "bitcoin" / "bitcoin_raw.csv"),
        "quality_path": str(QUALITY_DIR / "bitcoin_quality.json"),
    },
    {
        "key": "nvidia",
        "symbol": "NVDA",
        "name": "NVIDIA",
        "asset_type": "EQUITY",
        "env_ticker": "YAHOO_NVIDIA_TICKER",
        "raw_path": str(RAW_DIR / "nvidia" / "nvidia_raw.csv"),
        "quality_path": str(QUALITY_DIR / "nvidia_quality.json"),
    },
]

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _require_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        print(f"ERROR: Environment variable '{key}' is not set or empty.")
        sys.exit(1)
    return value


def _get_config() -> dict[str, Any]:
    return {
        "supabase_url": _require_env("SUPABASE_URL"),
        "supabase_key": _require_env("SUPABASE_SERVICE_ROLE_KEY"),
        "start_date": os.getenv("START_DATE", "2020-01-01"),
        "end_date":   os.getenv("END_DATE", "2026-12-31"),
    }


def _get_supabase_client(config: dict[str, Any]) -> Client:
    return create_client(config["supabase_url"], config["supabase_key"])


# ---------------------------------------------------------------------------
# SHA-256 hash of CSV content (for dataset reproducibility tracking)
# ---------------------------------------------------------------------------


def compute_file_hash(csv_path: str) -> str:
    """Return SHA-256 hex digest of the file at csv_path."""
    h = hashlib.sha256()
    with open(csv_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Column discovery helpers (shared by Yahoo and CSV modes)
# ---------------------------------------------------------------------------

_COLUMN_ALIASES: dict[str, str] = {
    "date": "date", "datetime": "date", "trade date": "date",
    "open": "open", "open price": "open", "usd open": "open",
    "high": "high", "high price": "high", "usd high": "high",
    "low": "low",   "low price": "low",   "usd low": "low",
    "close": "close", "last": "close", "closing price": "close",
    "adj close": "close", "usd close": "close", "price": "close",
    "last price": "close", "settle": "close", "value": "close",
    "volume": "volume", "volume (btc)": "volume", "volume btc": "volume",
    "shares traded": "volume", "trade volume": "volume",
    # CSV-specific
    "asset": "asset", "ticker": "asset", "symbol": "asset",
    "asset_type": "asset_type", "type": "asset_type",
}


def _discover_columns(df: pd.DataFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lower_cols = {col.lower(): col for col in df.columns}
    for lower_col, actual_col in lower_cols.items():
        canonical = _COLUMN_ALIASES.get(lower_col)
        if canonical and canonical not in mapping:
            mapping[canonical] = actual_col
    return mapping


# ---------------------------------------------------------------------------
# CSV ingestion – Step A: load and validate CSV format
# ---------------------------------------------------------------------------


def load_and_validate_csv(csv_path: str) -> pd.DataFrame:
    """
    Load a user-provided CSV file, validate its structure, and return a
    raw DataFrame.

    Raises ValueError immediately if:
      - File does not exist or is not a .csv
      - Required columns (date, asset, close) are missing
      - Dataset is completely empty
      - Date column cannot be parsed
      - Close column is entirely non-numeric
      - Unsupported file extension

    Does NOT silently fix bad data.
    """
    path = Path(csv_path)

    if not path.exists():
        raise ValueError(f"File not found: {csv_path}")

    if path.suffix.lower() not in (".csv", ".tsv"):
        raise ValueError(
            f"Unsupported file format '{path.suffix}'. Only .csv files are supported."
        )

    try:
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        raw = pd.read_csv(csv_path, sep=sep)
    except Exception as exc:
        raise ValueError(f"Failed to read CSV: {exc}") from exc

    if raw.empty:
        raise ValueError("CSV file is empty. At least one data row is required.")

    # Discover columns
    col_map = _discover_columns(raw)

    # Validate required columns
    missing = []
    for req in ("date", "asset", "close"):
        if req not in col_map:
            missing.append(req)
    if missing:
        raise ValueError(
            f"CSV is missing required column(s): {missing}.\n"
            f"Available columns: {list(raw.columns)}"
        )

    # Validate date parseable
    date_col = col_map["date"]
    try:
        test_dates = pd.to_datetime(raw[date_col], errors="coerce")
        n_bad = int(test_dates.isna().sum())
        if n_bad == len(raw):
            raise ValueError(
                f"Column '{date_col}' cannot be parsed as dates. "
                "Expected format: YYYY-MM-DD."
            )
        if n_bad > 0:
            print(f"  WARNING: {n_bad} row(s) have unparseable dates — "
                  "they will be rejected during validation.")
    except ValueError:
        raise

    # Validate close is numeric
    close_col = col_map["close"]
    test_close = pd.to_numeric(raw[close_col], errors="coerce")
    if test_close.isna().all():
        raise ValueError(
            f"Column '{close_col}' (close price) contains no numeric values."
        )

    return raw


# ---------------------------------------------------------------------------
# CSV ingestion – Step B: resolve asset_type (interactive if missing)
# ---------------------------------------------------------------------------


def resolve_asset_types(
    raw_df: pd.DataFrame,
    client: Client,
    asset_type_overrides: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """
    Determine the (name, asset_type) for each distinct asset in raw_df.

    Hierarchy:
      0. Explicit UI/caller asset_type_overrides (if provided).
      1. If CSV has an asset_type column, validate it against VALID_ASSET_TYPES.
      2. If asset already exists in the assets table with a valid asset_type,
         use its existing type (with conflict confirmation if CSV differs).
      3. If no type available: prompt the user interactively.

    Returns
    -------
    dict[symbol -> {name, asset_type}]

    Never silently defaults any asset to EQUITY.
    """
    col_map = _discover_columns(raw_df)
    asset_col = col_map.get("asset")
    type_col  = col_map.get("asset_type")

    symbols = sorted(raw_df[asset_col].dropna().astype(str).str.upper().unique())

    if not symbols:
        raise ValueError("No asset symbols found in CSV.")

    # Load existing global assets from DB
    existing: dict[str, dict] = {}
    try:
        rows = client.table("assets").select("symbol, name, asset_type").execute().data
        for r in (rows or []):
            existing[r["symbol"].upper()] = r
    except Exception:
        pass  # DB lookup failure is non-fatal; we will prompt

    print()
    print("  Assets detected in CSV:")
    for i, sym in enumerate(symbols, 1):
        print(f"    {i}. {sym}")
    print()

    result: dict[str, dict[str, str]] = {}

    for sym in symbols:
        csv_type: str | None = None

        # Check explicit overrides first
        if asset_type_overrides and sym in asset_type_overrides:
            resolved_type = str(asset_type_overrides[sym]).upper()
            db_name = existing.get(sym, {}).get("name")
            asset_name = db_name if db_name else sym
            result[sym] = {"name": asset_name, "asset_type": resolved_type}
            continue

        # Try to get asset_type from CSV column
        if type_col is not None:
            mask = raw_df[asset_col].astype(str).str.upper() == sym
            type_vals = raw_df.loc[mask, type_col].dropna().astype(str).str.upper().unique()
            if len(type_vals) == 1:
                csv_type = type_vals[0]
            elif len(type_vals) > 1:
                print(f"  WARNING: Multiple asset_type values for {sym}: {list(type_vals)}")
                csv_type = None

        db_type: str | None = existing.get(sym, {}).get("asset_type")
        db_name: str | None = existing.get(sym, {}).get("name")

        if csv_type and csv_type not in VALID_ASSET_TYPES:
            print(f"  WARNING: Invalid asset_type '{csv_type}' for {sym} in CSV.")
            csv_type = None

        if csv_type and db_type and csv_type != db_type:
            # Conflict between CSV type and existing DB type
            print()
            print(f"  CONFLICT for asset '{sym}':")
            print(f"    Existing DB type : {db_type}")
            print(f"    CSV-provided type: {csv_type}")
            answer = _prompt_with_choices(
                f"  Which asset_type should be used for {sym}?",
                [db_type, csv_type]
            )
            resolved_type = answer
        elif db_type:
            # Asset already exists in DB with a valid type — use it
            resolved_type = db_type
            print(f"  {sym}: using existing global asset_type = {db_type}")
        elif csv_type:
            # CSV has a valid type and no DB record exists
            resolved_type = csv_type
            print(f"  {sym}: using CSV-provided asset_type = {csv_type}")
        else:
            # Must prompt
            resolved_type = _prompt_asset_type(sym)

        # Determine asset name
        if db_name:
            asset_name = db_name
        else:
            asset_name = sym  # Default name = symbol; can be refined later

        result[sym] = {"name": asset_name, "asset_type": resolved_type}

    print()
    return result


def _prompt_asset_type(symbol: str) -> str:
    """
    Interactively prompt for a valid asset_type for the given symbol.
    Only accepts EQUITY, COMMODITY, CRYPTOCURRENCY (case-insensitive).
    """
    types = sorted(VALID_ASSET_TYPES)
    while True:
        print(f"  Enter asset type for {symbol}:")
        print(f"  Options: {', '.join(types)}")
        answer = input(f"  > ").strip().upper()
        if answer in VALID_ASSET_TYPES:
            return answer
        print(f"  Invalid. Enter one of: {', '.join(types)}")


def _prompt_with_choices(prompt: str, choices: list[str]) -> str:
    """Prompt the user to choose one of the provided choices."""
    for i, c in enumerate(choices, 1):
        print(f"    {i}. {c}")
    while True:
        answer = input(f"  > ").strip()
        if answer in choices:
            return answer
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print(f"  Please enter {' or '.join(choices)} (or 1-{len(choices)})")


# ---------------------------------------------------------------------------
# CSV ingestion – Step C: split CSV by asset, clean and validate each
# ---------------------------------------------------------------------------


def split_csv_by_asset(
    raw_df: pd.DataFrame,
    asset_types: dict[str, dict[str, str]],
) -> dict[str, tuple[pd.DataFrame, dict, dict]]:
    """
    Split the multi-asset CSV into per-asset DataFrames.
    Apply clean_data() and validate_data() to each.

    Returns
    -------
    dict[symbol -> (valid_df, cleaning_report, validation_report)]

    Raises ValueError if ANY asset has zero valid rows after validation.
    """
    col_map  = _discover_columns(raw_df)
    asset_col = col_map["asset"]

    results: dict[str, tuple[pd.DataFrame, dict, dict]] = {}
    errors:  list[str] = []

    for sym in sorted(asset_types.keys()):
        mask = raw_df[asset_col].astype(str).str.upper() == sym
        df   = raw_df[mask].copy()

        if df.empty:
            errors.append(f"Asset '{sym}': no rows found in CSV.")
            continue

        # Drop the 'asset' and 'asset_type' columns before passing to clean_data
        drop_cols = []
        for canonical in ("asset", "asset_type"):
            actual = col_map.get(canonical)
            if actual and actual in df.columns:
                drop_cols.append(actual)
        df = df.drop(columns=drop_cols, errors="ignore")

        try:
            clean_df, cleaning_report = clean_data(df, sym)
            valid_df, validation_report = validate_data(
                clean_df, sym,
                start_date="1900-01-01",   # CSV mode: accept any date range
                end_date="2100-12-31",
            )
        except ValueError as exc:
            errors.append(f"Asset '{sym}': {exc}")
            continue

        if valid_df.empty:
            errors.append(
                f"Asset '{sym}': 0 valid rows after cleaning/validation. "
                f"Rejected: {validation_report.get('rows_rejected', '?')} rows."
            )
            continue

        results[sym] = (valid_df, cleaning_report, validation_report)

    if errors:
        raise ValueError(
            "CSV validation failed:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    return results


# ---------------------------------------------------------------------------
# Step 2 – clean_data  (unchanged from original; works for single-asset df)
# ---------------------------------------------------------------------------


def clean_data(df: pd.DataFrame, asset_name: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Clean the raw DataFrame and return (cleaned_df, cleaning_report).
    Identical logic to the original Layer 1 implementation.
    """
    report: dict[str, Any] = {
        "duplicate_rows_removed": 0,
        "missing_values_detected": {},
        "negative_price_rows": 0,
        "invalid_numeric_rows": 0,
        "rows_before": len(df),
        "rows_after": 0,
        "warnings": [],
    }

    col_map = _discover_columns(df)

    date_col = col_map.get("date")
    if date_col is None:
        for c in df.columns:
            if "date" in c.lower():
                date_col = c
                col_map["date"] = c
                break
    if date_col is None:
        raise ValueError(
            f"[{asset_name}] Cannot identify a date column in: {list(df.columns)}"
        )

    available_canonical = set(col_map.keys()) - {"date"}
    missing_canonical = set(OHLCV_COLUMNS) - available_canonical
    if missing_canonical:
        msg = (
            f"[{asset_name}] Required OHLCV columns not found: "
            f"{missing_canonical}. Available: {list(df.columns)}"
        )
        if "close" in missing_canonical:
            raise ValueError(msg)
        report["warnings"].append(msg)

    rename_map = {actual: canonical for canonical, actual in col_map.items()}
    df = df.rename(columns=rename_map)

    keep_cols = ["date"] + OHLCV_COLUMNS
    for col in keep_cols:
        if col not in df.columns:
            df[col] = np.nan
    df = df[keep_cols].copy()

    before = len(df)
    df = df.drop_duplicates()
    report["duplicate_rows_removed"] = before - len(df)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    for col in OHLCV_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["date"] + OHLCV_COLUMNS:
        n_missing = int(df[col].isna().sum())
        if n_missing > 0:
            report["missing_values_detected"][col] = n_missing
            if col in ("open", "high", "low", "close"):
                report["warnings"].append(
                    f"[{asset_name}] Column '{col}' has {n_missing} missing values."
                )

    price_cols = ["open", "high", "low", "close"]
    neg_mask = pd.Series(False, index=df.index)
    for col in price_cols:
        neg_mask |= (df[col].notna() & (df[col] < 0))
    n_negative = int(neg_mask.sum())
    report["negative_price_rows"] = n_negative
    if n_negative > 0:
        report["warnings"].append(
            f"[{asset_name}] {n_negative} row(s) with negative prices detected."
        )

    neg_vol_mask = df["volume"].notna() & (df["volume"] < 0)
    n_neg_vol = int(neg_vol_mask.sum())
    if n_neg_vol > 0:
        report["warnings"].append(
            f"[{asset_name}] {n_neg_vol} row(s) with negative volume."
        )

    report["rows_after"] = len(df)
    return df, report


# ---------------------------------------------------------------------------
# Step 3 – validate_data  (unchanged from original)
# ---------------------------------------------------------------------------


def validate_data(
    df: pd.DataFrame,
    asset_name: str,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate cleaned data. Identical logic to original implementation."""
    report: dict[str, Any] = {
        "rows_in": len(df),
        "null_date_rows": 0,
        "out_of_range_date_rows": 0,
        "duplicate_date_rows": 0,
        "invalid_ohlc_rows": 0,
        "negative_price_rows": 0,
        "negative_volume_rows": 0,
        "rows_rejected": 0,
        "rows_valid": 0,
        "warnings": [],
    }

    rejected_mask = pd.Series(False, index=df.index)

    null_date_mask = df["date"].isna()
    n_null = int(null_date_mask.sum())
    report["null_date_rows"] = n_null
    if n_null:
        report["warnings"].append(f"[{asset_name}] {n_null} row(s) with null date – rejected.")
    rejected_mask |= null_date_mask

    req_start = pd.to_datetime(start_date).date()
    req_end   = pd.to_datetime(end_date).date()
    oor_mask  = df["date"].notna() & (
        (df["date"] < req_start) | (df["date"] > req_end)
    )
    n_oor = int(oor_mask.sum())
    report["out_of_range_date_rows"] = n_oor
    if n_oor:
        report["warnings"].append(
            f"[{asset_name}] {n_oor} row(s) outside requested date range – rejected."
        )
    rejected_mask |= oor_mask

    dup_date_mask = df["date"].duplicated(keep="first")
    n_dup = int(dup_date_mask.sum())
    report["duplicate_date_rows"] = n_dup
    if n_dup:
        report["warnings"].append(
            f"[{asset_name}] {n_dup} duplicate date(s) found; keeping first."
        )
    rejected_mask |= dup_date_mask

    price_cols = ["open", "high", "low", "close"]
    has_prices = df[price_cols].notna().all(axis=1)
    evaluable  = ~rejected_mask & has_prices
    ohlc_invalid = evaluable & (
        (df["high"] < df["open"])  |
        (df["high"] < df["close"]) |
        (df["high"] < df["low"])   |
        (df["low"]  > df["open"])  |
        (df["low"]  > df["close"])
    )
    n_ohlc = int(ohlc_invalid.sum())
    report["invalid_ohlc_rows"] = n_ohlc
    if n_ohlc:
        report["warnings"].append(
            f"[{asset_name}] {n_ohlc} row(s) fail OHLC constraints – rejected."
        )
    rejected_mask |= ohlc_invalid

    neg_price = evaluable & ~ohlc_invalid & (df[price_cols] < 0).any(axis=1)
    n_neg = int(neg_price.sum())
    report["negative_price_rows"] = n_neg
    if n_neg:
        report["warnings"].append(
            f"[{asset_name}] {n_neg} row(s) with negative prices – rejected."
        )
    rejected_mask |= neg_price

    neg_vol = df["volume"].notna() & (df["volume"] < 0)
    n_neg_vol = int(neg_vol.sum())
    report["negative_volume_rows"] = n_neg_vol
    if n_neg_vol:
        report["warnings"].append(
            f"[{asset_name}] {n_neg_vol} row(s) with negative volume – rejected."
        )
    rejected_mask |= neg_vol

    valid_df = df[~rejected_mask].copy()
    report["rows_rejected"] = int(rejected_mask.sum())
    report["rows_valid"] = len(valid_df)
    return valid_df, report


# ---------------------------------------------------------------------------
# Step 4 – normalize_data
# ---------------------------------------------------------------------------


def normalize_data_csv(
    df: pd.DataFrame,
    symbol: str,
    asset_info: dict[str, str],
    csv_filename: str,
) -> pd.DataFrame:
    """Normalize a per-asset validated DataFrame for CSV mode."""
    n = len(df)
    normalized = pd.DataFrame({
        "asset":          [symbol]            * n,
        "asset_type":     [asset_info["asset_type"]] * n,
        "date":           df["date"].values,
        "open":           df["open"].values,
        "high":           df["high"].values,
        "low":            df["low"].values,
        "close":          df["close"].values,
        "volume":         df["volume"].values,
        "source":         [SOURCE_CSV]        * n,
        "source_dataset": [csv_filename]      * n,
    })
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.date
    return normalized.reset_index(drop=True)


def normalize_data(df: pd.DataFrame, asset: dict[str, str]) -> pd.DataFrame:
    """Normalize for legacy Yahoo Finance mode (unchanged)."""
    import os
    ticker = os.getenv(asset.get("env_ticker", ""), "")
    n = len(df)
    normalized = pd.DataFrame({
        "asset":          [asset["symbol"]]   * n,
        "asset_type":     [asset["asset_type"]] * n,
        "date":           df["date"].values,
        "open":           df["open"].values,
        "high":           df["high"].values,
        "low":            df["low"].values,
        "close":          df["close"].values,
        "volume":         df["volume"].values,
        "source":         [SOURCE_NAME]       * n,
        "source_dataset": [ticker]            * n,
    })
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.date
    return normalized.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 5 – save_to_supabase (CSV batch mode)
# ---------------------------------------------------------------------------


def _upsert_asset(
    client: Client,
    symbol: str,
    name: str,
    asset_type: str,
    source: str,
    source_dataset: str,
) -> str:
    """Upsert an asset record and return its UUID."""
    client.table("assets").upsert(
        {
            "symbol":         symbol,
            "name":           name,
            "asset_type":     asset_type,
            "source":         source,
            "source_dataset": source_dataset,
            "updated_at":     datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="symbol",
    ).execute()
    result = (
        client.table("assets")
        .select("id")
        .eq("symbol", symbol)
        .single()
        .execute()
    )
    return result.data["id"]


def _register_batch_asset(client: Client, batch_id: str, asset_id: str) -> None:
    client.table("batch_assets").upsert(
        {"batch_id": batch_id, "asset_id": asset_id},
        on_conflict="batch_id,asset_id",
    ).execute()


def save_market_prices_batch(
    client: Client,
    normalized_df: pd.DataFrame,
    asset_id: str,
    batch_id: str,
) -> int:
    """Upsert market_prices rows with batch_id."""
    rows: list[dict] = []
    for _, row in normalized_df.iterrows():
        rows.append({
            "batch_id":       batch_id,
            "asset_id":       asset_id,
            "date":           str(row["date"]),
            "open":           _safe_float(row["open"]),
            "high":           _safe_float(row["high"]),
            "low":            _safe_float(row["low"]),
            "close":          _safe_float(row["close"]),
            "volume":         _safe_float(row["volume"]),
            "source":         row["source"],
            "source_dataset": row["source_dataset"],
            "ingested_at":    datetime.now(timezone.utc).isoformat(),
        })

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i : i + BATCH_SIZE]
        client.table("market_prices").upsert(
            chunk, on_conflict="batch_id,asset_id,date"
        ).execute()
        inserted += len(chunk)
    return inserted


# ---------------------------------------------------------------------------
# Ingestion run tracking (batch-aware)
# ---------------------------------------------------------------------------


def _create_ingestion_run(
    client: Client,
    asset_id: str,
    batch_id: str,
    source: str,
    source_dataset: str,
    start_date: str,
    end_date: str,
) -> str:
    result = client.table("ingestion_runs").insert({
        "batch_id":             batch_id,
        "asset_id":             asset_id,
        "source":               source,
        "source_dataset":       source_dataset,
        "requested_start_date": start_date,
        "requested_end_date":   end_date,
        "status":               "RUNNING",
    }).execute()
    return result.data[0]["id"]


def _update_ingestion_run(
    client: Client,
    run_id: str,
    rows_downloaded: int,
    rows_after_cleaning: int,
    rows_rejected: int,
    rows_inserted: int,
    status: str,
    error_message: str | None = None,
) -> None:
    client.table("ingestion_runs").update({
        "rows_downloaded":     rows_downloaded,
        "rows_after_cleaning": rows_after_cleaning,
        "rows_rejected":       rows_rejected,
        "rows_inserted":       rows_inserted,
        "status":              status,
        "error_message":       error_message,
        "completed_at":        datetime.now(timezone.utc).isoformat(),
    }).eq("id", run_id).execute()


# ---------------------------------------------------------------------------
# CSV pipeline entry point  (called by run_pipeline.py)
# ---------------------------------------------------------------------------


def ingest_csv(
    csv_path: str,
    batch_id: str,
    client: Client,
    asset_type_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Full Layer 1 CSV ingestion for one batch.

    Flow
    ----
    1. Compute SHA-256 hash of CSV.
    2. Load and validate CSV structure.
    3. Resolve asset types (interactive if needed, or via asset_type_overrides).
    4. Per-asset: clean → validate → normalize.
    5. Per-asset: upsert asset, register in batch_assets, save market_prices.
    6. Create ingestion_run records.

    CSV validation is completed BEFORE any DB writes.
    If validation fails, no rows are written.

    Returns
    -------
    dict with keys:
      assets_processed : list of symbols
      total_rows       : int
      per_asset        : dict[symbol -> {rows_inserted, asset_id, status}]
    """
    csv_path = str(csv_path)

    # ---- Step 1: CSV structure validation (before any DB write) ----
    print("  Validating CSV structure...")
    raw_df = load_and_validate_csv(csv_path)
    print(f"  CSV loaded: {len(raw_df)} rows.")

    # ---- Step 2: Resolve asset types (may prompt interactively) ----
    print("  Resolving asset types...")
    asset_types = resolve_asset_types(raw_df, client, asset_type_overrides=asset_type_overrides)

    # ---- Step 3: Per-asset clean & validate (all must pass before any DB write) ----
    print("  Validating per-asset data quality...")
    per_asset_data = split_csv_by_asset(raw_df, asset_types)
    print(f"  All {len(per_asset_data)} asset(s) passed validation.")

    # ---- All validation complete — now write to DB ----
    csv_filename = Path(csv_path).name
    results: dict[str, Any] = {}
    total_rows = 0

    for sym, (valid_df, cleaning_report, validation_report) in per_asset_data.items():
        asset_info = asset_types[sym]
        run_id: str | None = None

        try:
            # Upsert global asset record
            asset_id = _upsert_asset(
                client,
                symbol=sym,
                name=asset_info["name"],
                asset_type=asset_info["asset_type"],
                source=SOURCE_CSV,
                source_dataset=csv_filename,
            )

            # Register in batch_assets
            _register_batch_asset(client, batch_id, asset_id)

            # Create ingestion run
            dates = valid_df["date"].dropna()
            start = str(dates.min()) if not dates.empty else "unknown"
            end   = str(dates.max()) if not dates.empty else "unknown"

            run_id = _create_ingestion_run(
                client, asset_id, batch_id,
                SOURCE_CSV, csv_filename, start, end,
            )

            # Normalize
            normalized_df = normalize_data_csv(valid_df, sym, asset_info, csv_filename)

            # Save market prices
            rows_inserted = save_market_prices_batch(client, normalized_df, asset_id, batch_id)

            has_warnings = bool(
                cleaning_report.get("warnings") or validation_report.get("warnings")
            ) or validation_report.get("rows_rejected", 0) > 0

            status = "SUCCESS_WITH_WARNINGS" if has_warnings else "SUCCESS"
            _update_ingestion_run(
                client, run_id,
                rows_downloaded=len(valid_df) + validation_report.get("rows_rejected", 0),
                rows_after_cleaning=cleaning_report.get("rows_after", len(valid_df)),
                rows_rejected=validation_report.get("rows_rejected", 0),
                rows_inserted=rows_inserted,
                status=status,
            )

            results[sym] = {
                "asset_id": asset_id,
                "rows_inserted": rows_inserted,
                "status": status,
            }
            total_rows += rows_inserted

        except Exception as exc:
            if run_id:
                try:
                    _update_ingestion_run(
                        client, run_id,
                        rows_downloaded=0, rows_after_cleaning=0,
                        rows_rejected=0, rows_inserted=0,
                        status="FAILED", error_message=str(exc),
                    )
                except Exception:
                    pass
            raise RuntimeError(f"Failed to ingest asset '{sym}': {exc}") from exc

    return {
        "assets_processed": list(per_asset_data.keys()),
        "total_rows": total_rows,
        "per_asset": results,
    }


# ---------------------------------------------------------------------------
# Quality report (used by legacy Yahoo mode)
# ---------------------------------------------------------------------------


def save_quality_report(
    asset: dict[str, str],
    rows_downloaded: int,
    rows_after_cleaning: int,
    rows_rejected: int,
    cleaning_report: dict[str, Any],
    validation_report: dict[str, Any],
    status: str,
    first_date: str | None,
    last_date: str | None,
) -> None:
    quality_path = asset.get("quality_path", str(QUALITY_DIR / f"{asset.get('key','unknown')}_quality.json"))
    report = {
        "asset": asset.get("name"),
        "symbol": asset.get("symbol"),
        "rows_downloaded": rows_downloaded,
        "rows_after_cleaning": rows_after_cleaning,
        "rows_rejected": rows_rejected,
        "rows_valid": rows_after_cleaning - rows_rejected,
        "first_date": first_date,
        "last_date": last_date,
        "status": status,
        "warnings": cleaning_report.get("warnings", []) + validation_report.get("warnings", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Legacy Yahoo Finance mode – fetch_data (unchanged)
# ---------------------------------------------------------------------------


def _next_day(date_str: str) -> str:
    from datetime import timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return str(d + timedelta(days=1))


def fetch_data(asset: dict[str, str], config: dict[str, Any]) -> pd.DataFrame:
    """Download historical OHLCV data from Yahoo Finance (legacy mode only)."""
    import yfinance as yf
    ticker = _require_env(asset["env_ticker"])
    df = yf.download(
        tickers=ticker,
        start=config["start_date"],
        end=_next_day(config["end_date"]),
        auto_adjust=True,
        progress=False,
        multi_level_index=False,
    )
    if df is None or df.empty:
        raise ValueError(f"Yahoo Finance returned no data for '{ticker}'.")
    df = df.reset_index()
    Path(asset["raw_path"]).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(asset["raw_path"], index=False)
    return df


def save_to_supabase(
    normalized_df: pd.DataFrame,
    asset: dict[str, str],
    config: dict[str, Any],
    batch_id: str | None = None,
) -> dict[str, Any]:
    """Legacy Yahoo Finance save path. Batch_id is passed through if available."""
    client = _get_supabase_client(config)
    ticker = os.getenv(asset.get("env_ticker", ""), "")

    asset_record = {
        "symbol":         asset["symbol"],
        "name":           asset["name"],
        "asset_type":     asset["asset_type"],
        "source":         SOURCE_NAME,
        "source_dataset": ticker,
        "updated_at":     datetime.now(timezone.utc).isoformat(),
    }
    client.table("assets").upsert(asset_record, on_conflict="symbol").execute()
    result = (
        client.table("assets")
        .select("id")
        .eq("symbol", asset["symbol"])
        .single()
        .execute()
    )
    asset_id: str = result.data["id"]

    if batch_id:
        _register_batch_asset(client, batch_id, asset_id)

    rows: list[dict[str, Any]] = []
    for _, row in normalized_df.iterrows():
        r = {
            "asset_id":       asset_id,
            "date":           str(row["date"]),
            "open":           _safe_float(row["open"]),
            "high":           _safe_float(row["high"]),
            "low":            _safe_float(row["low"]),
            "close":          _safe_float(row["close"]),
            "volume":         _safe_float(row["volume"]),
            "source":         row["source"],
            "source_dataset": row["source_dataset"],
            "ingested_at":    datetime.now(timezone.utc).isoformat(),
        }
        if batch_id:
            r["batch_id"] = batch_id
        rows.append(r)

    conflict_cols = "batch_id,asset_id,date" if batch_id else "asset_id,date"
    rows_inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i : i + BATCH_SIZE]
        client.table("market_prices").upsert(chunk, on_conflict=conflict_cols).execute()
        rows_inserted += len(chunk)

    return {"asset_id": asset_id, "rows_inserted": rows_inserted}


# ---------------------------------------------------------------------------
# Legacy Yahoo pipeline orchestrator
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """
    Execute the original Yahoo Finance ingestion pipeline.
    Retains full backwards compatibility with the original implementation.
    """
    config = _get_config()
    client = _get_supabase_client(config)

    print("=" * 40)
    print("Financial Data Ingestion (Yahoo Finance)")
    print("=" * 40)
    print()

    results: list[tuple[str, str]] = []

    for asset in LEGACY_ASSETS:
        label = asset["name"]
        print(f"[{label}]")

        rows_downloaded = 0
        rows_after_cleaning = 0
        rows_rejected = 0
        rows_inserted = 0
        cleaning_report: dict[str, Any] = {}
        validation_report: dict[str, Any] = {}
        first_date: str | None = None
        last_date: str | None = None
        run_id: str | None = None
        status = "FAILED"
        error_message: str | None = None

        try:
            ticker = os.getenv(asset["env_ticker"], "")
            asset_record = {
                "symbol": asset["symbol"], "name": asset["name"],
                "asset_type": asset["asset_type"], "source": SOURCE_NAME,
                "source_dataset": ticker,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            client.table("assets").upsert(asset_record, on_conflict="symbol").execute()
            id_result = (
                client.table("assets").select("id")
                .eq("symbol", asset["symbol"]).single().execute()
            )
            asset_id = id_result.data["id"]

            run_id = _create_ingestion_run(
                client, asset_id, None, SOURCE_NAME, ticker,
                config["start_date"], config["end_date"],
            ) if False else None  # legacy mode: no batch_id

            # Use original ingestion_runs insert (without batch_id)
            res = client.table("ingestion_runs").insert({
                "asset_id":             asset_id,
                "source":               SOURCE_NAME,
                "source_dataset":       ticker,
                "requested_start_date": config["start_date"],
                "requested_end_date":   config["end_date"],
                "status":               "RUNNING",
            }).execute()
            run_id = res.data[0]["id"]

            print("  Downloading...")
            raw_df = fetch_data(asset, config)
            rows_downloaded = len(raw_df)

            print("  Cleaning...")
            clean_df, cleaning_report = clean_data(raw_df, label)
            rows_after_cleaning = len(clean_df)

            print("  Validating...")
            valid_df, validation_report = validate_data(
                clean_df, label, config["start_date"], config["end_date"]
            )
            rows_rejected = validation_report["rows_rejected"]

            print("  Normalizing...")
            normalized_df = normalize_data(valid_df, asset)

            if not normalized_df.empty:
                dates = normalized_df["date"].dropna()
                first_date = str(dates.min()) if not dates.empty else None
                last_date  = str(dates.max()) if not dates.empty else None

            print("  Saving to Supabase...")
            upsert_result = save_to_supabase(normalized_df, asset, config)
            rows_inserted = upsert_result["rows_inserted"]

            has_warnings = bool(
                cleaning_report.get("warnings") or validation_report.get("warnings")
            ) or rows_rejected > 0
            status = "SUCCESS_WITH_WARNINGS" if has_warnings else "SUCCESS"
            print(f"  {status}")

        except Exception as exc:
            status = "FAILED"
            error_message = str(exc)
            print(f"  FAILED: {error_message}")

        finally:
            save_quality_report(
                asset=asset,
                rows_downloaded=rows_downloaded,
                rows_after_cleaning=rows_after_cleaning,
                rows_rejected=rows_rejected,
                cleaning_report=cleaning_report,
                validation_report=validation_report,
                status=status,
                first_date=first_date,
                last_date=last_date,
            )
            if run_id:
                try:
                    _update_ingestion_run(
                        client, run_id,
                        rows_downloaded, rows_after_cleaning,
                        rows_rejected, rows_inserted, status, error_message,
                    )
                except Exception as ue:
                    print(f"  WARNING: Could not update ingestion_run: {ue}")
            results.append((label, status))
            print()

    print("=" * 40)
    print("SUMMARY")
    print("=" * 40)
    for name, st in results:
        print(f"  {name:<12} {st}")
    print()
    print("  Data stored in Supabase.")
    print("=" * 40)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_pipeline()
