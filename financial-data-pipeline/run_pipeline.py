"""
run_pipeline.py -- Batch-Orchestrated Pipeline Runner
======================================================
Runs all 7 layers sequentially for a single batch_id.

Usage
-----
    python run_pipeline.py                          # prompts for batch_id
    python run_pipeline.py LEGACY_EXISTING_RUN      # pass as argument
    python run_pipeline.py NEW_CSV_RUN path/to/data.csv

Modes
-----
  LEGACY mode  : if market_prices already exist for batch_id, Layer 1 is skipped
                 and Layers 2-7 run against the existing data.

  CSV mode     : if market_prices do NOT exist, you must supply a CSV path
                 (passed as the second CLI argument, or prompted interactively).

Flow
----
    Layer 1  ingest.py            -> market_prices
    Layer 2  quant_engine.py      -> asset_indicators, asset_statistics, asset_correlations
    Layer 3  strategy_engine.py   -> strategy_signals
    Layer 4  backtest_engine.py   -> backtest_runs, backtest_equity, backtest_trades, backtest_metrics
    Layer 5  robustness_engine.py -> robustness_results, market_regimes, strategy_regime_performance
    Layer 6  portfolio_optimizer.py -> portfolio_optimization_runs, portfolio_allocations, portfolio_results
    Layer 7  qubo_optimizer.py    -> qubo_runs, qubo_variables, qubo_matrix, qubo_results

Rules
-----
- Every layer receives the same batch_id.
- No layer may be skipped if a prior layer failed.
- Layer 1 is skipped when market_prices already exist for this batch_id.
- All seven layers MUST use the same batch_id; data is never mixed.
"""

from __future__ import annotations

import sys
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# IPv4 patch
# ---------------------------------------------------------------------------
import socket as _socket

_orig_gai = _socket.getaddrinfo


def _ipv4_first(h, p, f=0, t=0, pr=0, fl=0):
    r = _orig_gai(h, p, f, t, pr, fl)
    return sorted(r, key=lambda x: 0 if x[0] == _socket.AF_INET else 1)


_socket.getaddrinfo = _ipv4_first


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

def _get_supabase_client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def _separator(title: str = "") -> None:
    line = "=" * 60
    if title:
        print(f"\n{line}")
        print(f"  {title}")
        print(line)
    else:
        print(line)


def _check_market_prices_exist(client, batch_id: str) -> bool:
    """Return True if market_prices already has rows for this batch_id."""
    result = (
        client.table("market_prices")
        .select("asset_id")
        .eq("batch_id", batch_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def _register_batch(client, batch_id: str) -> None:
    """Ensure this batch_id exists in analysis_batches with status=RUNNING."""
    try:
        existing = (
            client.table("analysis_batches")
            .select("batch_id")
            .eq("batch_id", batch_id)
            .execute()
        )
        if not existing.data:
            client.table("analysis_batches").insert({
                "batch_id":   batch_id,
                "batch_name": batch_id,
                "status":     "RUNNING",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        else:
            client.table("analysis_batches").update({
                "status":     "RUNNING",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }).eq("batch_id", batch_id).execute()
    except Exception as e:
        print(f"  [WARN] Could not register batch: {e}")


def _finalize_batch(client, batch_id: str, success: bool) -> None:
    """Mark the batch as COMPLETED or FAILED in analysis_batches."""
    try:
        client.table("analysis_batches").update({
            "status":       "COMPLETED" if success else "FAILED",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("batch_id", batch_id).execute()
    except Exception as e:
        print(f"  [WARN] Could not finalize batch: {e}")


# ---------------------------------------------------------------------------
# Layer runner
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Layer runner (records in batch_layer_runs table)
# ---------------------------------------------------------------------------

def _record_layer_start(client, batch_id: str, layer_num: int, name: str) -> None:
    try:
        client.table("batch_layer_runs").upsert({
            "batch_id":       batch_id,
            "layer_number":   layer_num,
            "layer_name":     name,
            "status":         "RUNNING",
            "started_at":     datetime.now(timezone.utc).isoformat(),
            "completed_at":   None,
            "error_message":  None,
            "metadata":       {}
        }, on_conflict="batch_id,layer_number").execute()
    except Exception as e:
        print(f"  [WARN] Could not record layer start: {e}")


def _record_layer_finish(client, batch_id: str, layer_num: int, success: bool, error_msg: str | None = None, rows: int | None = None) -> None:
    try:
        payload = {
            "status":        "COMPLETED" if success else "FAILED",
            "completed_at":  datetime.now(timezone.utc).isoformat(),
            "error_message": error_msg
        }
        if rows is not None:
            payload["rows_processed"] = rows
        client.table("batch_layer_runs").update(payload).eq("batch_id", batch_id).eq("layer_number", layer_num).execute()
    except Exception as e:
        print(f"  [WARN] Could not record layer finish: {e}")


def run_layer(layer_num: int, name: str, fn, batch_id: str, client=None) -> bool:
    """
    Run a single layer function. Returns True on success, False on failure.
    fn must accept a single positional argument: batch_id.
    """
    client = client or _get_supabase_client()
    _separator(f"LAYER {layer_num} -- {name}")
    print(f"  Started:  {_ts()}")
    _record_layer_start(client, batch_id, layer_num, name)

    t0 = time.time()
    try:
        fn(batch_id)
        elapsed = time.time() - t0
        print(f"\n  Finished: {_ts()}  ({elapsed:.1f}s)")
        print(f"  Status:   SUCCESS")
        _record_layer_finish(client, batch_id, layer_num, success=True)
        return True
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"\n  Finished: {_ts()}  ({elapsed:.1f}s)")
        print(f"  Status:   FAILED")
        print(f"  Error:    {exc}")
        _record_layer_finish(client, batch_id, layer_num, success=False, error_msg=str(exc))
        return False


# ---------------------------------------------------------------------------
# Layer 1 special handler
# ---------------------------------------------------------------------------

def run_layer1(client, batch_id: str, csv_path: str | None, asset_type_overrides: dict[str, str] | None = None) -> bool:
    """
    Handle Layer 1 with the following logic:
      - If market_prices already exist for batch_id: skip (legacy mode).
      - Otherwise: run CSV ingestion using csv_path.
        If csv_path is None, prompt interactively.
    Returns True on success, False on failure.
    """
    _separator("LAYER 1 -- DATA INGESTION")
    _record_layer_start(client, batch_id, 1, "DATA INGESTION")

    already_ingested = _check_market_prices_exist(client, batch_id)
    if already_ingested:
        print(f"  Skipped: market_prices already exist for batch_id={batch_id}")
        print(f"  Layers 2-7 will run against the existing data.")
        _record_layer_finish(client, batch_id, 1, success=True)
        return True

    # Need a CSV path
    if not csv_path:
        print()
        print("  No market data found for this batch.")
        print("  Please provide the path to your CSV file.")
        print("  Expected format: date,asset[,asset_type],open,high,low,close,volume")
        print()
        csv_path = input("  CSV file path: ").strip()

    if not csv_path or not os.path.isfile(csv_path):
        err = f"File not found: {csv_path}"
        print(f"  ERROR: {err}")
        _record_layer_finish(client, batch_id, 1, success=False, error_msg=err)
        return False

    print(f"  Started:  {_ts()}")
    print(f"  CSV:      {csv_path}")
    t0 = time.time()
    try:
        import ingest
        result = ingest.ingest_csv(csv_path, batch_id, client, asset_type_overrides=asset_type_overrides)
        elapsed = time.time() - t0
        print(f"\n  Assets:   {result['assets_processed']}")
        print(f"  Rows:     {result['total_rows']:,}")
        print(f"  Finished: {_ts()}  ({elapsed:.1f}s)")
        print(f"  Status:   SUCCESS")
        _record_layer_finish(client, batch_id, 1, success=True, rows=result.get("total_rows"))
        return True
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"\n  Finished: {_ts()}  ({elapsed:.1f}s)")
        print(f"  Status:   FAILED")
        print(f"  Error:    {exc}")
        _record_layer_finish(client, batch_id, 1, success=False, error_msg=str(exc))
        return False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(
    batch_id: str,
    csv_path: str | None = None,
    asset_type_overrides: dict[str, str] | None = None
) -> bool:
    """
    Run all 7 layers sequentially for the given batch_id.
    Stops immediately if any layer fails.
    Returns True if entire pipeline succeeded, False otherwise.
    """
    _separator()
    print(f"  QUANTITATIVE MULTI-ASSET PIPELINE")
    print(f"  Batch ID : {batch_id}")
    print(f"  Started  : {_ts()}")
    _separator()

    client = _get_supabase_client()

    # Register (or update) batch in analysis_batches
    _register_batch(client, batch_id)

    pipeline_success = True

    # ---- Layer 1 (special handling) -----------------------------------------
    print()
    ok = run_layer1(client, batch_id, csv_path, asset_type_overrides=asset_type_overrides)
    if not ok:
        print("\n  Pipeline halted at Layer 1.")
        _finalize_batch(client, batch_id, success=False)
        return False

    # ---- Layers 2-7 ----------------------------------------------------------
    import quant_engine
    import strategy_engine
    import backtest_engine
    import robustness_engine
    import portfolio_optimizer
    import qubo_optimizer

    layers = [
        (2, "QUANTITATIVE ANALYSIS",      quant_engine.run_quant_engine),
        (3, "STRATEGY ENGINE",            strategy_engine.run_strategy_engine),
        (4, "BACKTESTING ENGINE",         backtest_engine.run_backtest_engine),
        (5, "ROBUSTNESS & REGIME ENGINE", robustness_engine.run_robustness_engine),
        (6, "PORTFOLIO OPTIMIZATION",     portfolio_optimizer.main),
        (7, "QUBO OPTIMIZATION",          qubo_optimizer.main),
    ]

    for layer_num, name, fn in layers:
        print()
        ok = run_layer(layer_num, name, fn, batch_id, client=client)
        if not ok:
            print(f"\n  Pipeline halted at Layer {layer_num}.")
            pipeline_success = False
            break

    # ---- Final summary -------------------------------------------------------
    _separator()
    status_str = "SUCCESS" if pipeline_success else "FAILED"
    print(f"  PIPELINE {status_str}")
    print(f"  Batch ID : {batch_id}")
    print(f"  Finished : {_ts()}")
    _finalize_batch(client, batch_id, success=pipeline_success)

    if pipeline_success:
        try:
            import kg_pipeline_bridge
            kg_pipeline_bridge.sync_batch_to_neo4j(batch_id)
        except Exception as kg_err:
            print(f"  [WARN] Non-critical Knowledge Graph sync note: {kg_err}")

    return pipeline_success


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  QUANTITATIVE MULTI-ASSET PIPELINE")
    print("=" * 60)
    print()

    if len(sys.argv) >= 2:
        _batch_id = sys.argv[1].strip()
        _csv_path = sys.argv[2].strip() if len(sys.argv) >= 3 else None
    else:
        print("  To run an existing batch (Layers 2-7 only):")
        print("    python run_pipeline.py LEGACY_EXISTING_RUN")
        print()
        print("  To run a new CSV batch (all 7 layers):")
        print("    python run_pipeline.py MY_BATCH path/to/data.csv")
        print()
        _batch_id = input("  batch_id: ").strip()
        if not _batch_id:
            print("ERROR: batch_id cannot be empty.")
            sys.exit(1)
        _csv_path = None

    run_pipeline(_batch_id, _csv_path)
