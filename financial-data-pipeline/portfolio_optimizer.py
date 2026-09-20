"""
Portfolio Optimization Engine – Layer 6
=========================================
Reads historical returns from Layer 1 / Layer 2 (market_prices,
asset_indicators) and solves four classical portfolio optimization
objectives using scipy.optimize.minimize.

What this layer computes
------------------------
  1. MINIMUM_VOLATILITY  – minimise portfolio variance
  2. MAXIMUM_SHARPE      – maximise (return - rf) / volatility
  3. MAXIMUM_RETURN      – maximise expected return (reference bound)
  4. TARGET_RETURN       – minimise volatility subject to a return floor

Reference portfolios
---------------------
  • Equal-weight         33.3% / 33.3% / 33.3%
  • 100 % BTC / GOLD / NVDA

Discrete allocation (Layer 7 readiness)
-----------------------------------------
After classical optimization, weights are rounded to the nearest
allocation_step (default 0.10) while preserving sum = 1.
The continuous result is always preserved and stored separately.
Layer 7 can read both from portfolio_allocations.

Look-ahead guarantee
---------------------
All statistics (returns, covariance) are computed strictly from
data within [data_start, data_end]. No future observations are used.

Annualisation convention (same as Layer 2)
-------------------------------------------
  252 trading periods per year for all assets.
  daily_return = close_t / close_{t-1} - 1
  mu_i = mean(daily_return_i) * 252
  Sigma = cov(daily_returns) * 252

Run:
    python portfolio_optimizer.py

DISCLAIMER
----------
  All results are based on historical data only.
  Expected return and expected final value are historical estimates.
  They are NOT forecasts and do NOT predict future performance.
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
from scipy.optimize import minimize, OptimizeResult
from supabase import create_client, Client

load_dotenv()

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

ANNUALIZATION_FACTOR: int = 252  # trading periods per year (same as Layer 2)
PAGE_SIZE: int = 1000

# Objective labels (used as DB enum values)
OBJ_MIN_VOL       = "MINIMUM_VOLATILITY"
OBJ_MAX_SHARPE    = "MAXIMUM_SHARPE"
OBJ_MAX_RETURN    = "MAXIMUM_RETURN"
OBJ_TARGET_RETURN = "TARGET_RETURN"

ALL_OBJECTIVES = [OBJ_MIN_VOL, OBJ_MAX_SHARPE, OBJ_MAX_RETURN, OBJ_TARGET_RETURN]


# ---------------------------------------------------------------------------
# Configuration
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


def get_config() -> dict[str, Any]:
    """Load all configuration from environment variables."""
    return {
        "supabase_url":    _require_env("SUPABASE_URL"),
        "supabase_key":    _require_env("SUPABASE_SERVICE_ROLE_KEY"),
        "initial_capital": float(os.getenv("INITIAL_CAPITAL", "100000")),
        "risk_free_rate":  float(os.getenv("RISK_FREE_RATE", "0.0")),
        "lookback_days":   (
            int(os.getenv("LOOKBACK_DAYS"))
            if os.getenv("LOOKBACK_DAYS", "").strip()
            else None
        ),
        "allocation_step": float(os.getenv("ALLOCATION_STEP", "0.10")),
        "target_return":   (
            float(os.getenv("TARGET_RETURN"))
            if os.getenv("TARGET_RETURN", "").strip()
            else None
        ),
    }


def get_client(config: dict) -> Client:
    return create_client(config["supabase_url"], config["supabase_key"])


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


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


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Step 1 – load_assets
# ---------------------------------------------------------------------------


def load_assets(client: Client) -> pd.DataFrame:
    """
    Load asset master records from the `assets` table.

    Returns
    -------
    DataFrame with columns: asset_id, symbol, name, asset_type
    """
    rows = _paginate(client, "assets", "id, symbol, name, asset_type")
    if not rows:
        raise ValueError("assets table is empty. Run Layer 1 first.")
    df = pd.DataFrame(rows).rename(columns={"id": "asset_id"})
    return df


# ---------------------------------------------------------------------------
# Step 2 – load_market_returns
# ---------------------------------------------------------------------------


def load_market_returns(
    client: Client,
    lookback_days: int | None,
    batch_id: str,
) -> pd.DataFrame:
    """
    Load daily_return from asset_indicators (computed by Layer 2), scoped to batch_id.

    Parameters
    ----------
    lookback_days : if set, only the most recent N calendar days are loaded.
                   If None, the full history is used.
    batch_id      : isolates this load to the current pipeline run.

    Returns
    -------
    DataFrame with columns: asset_id, date, daily_return
    """
    rows = _paginate_batch(client, "asset_indicators", "asset_id, date, daily_return", batch_id)
    if not rows:
        raise ValueError(
            f"asset_indicators is empty for batch_id={batch_id}. Run Layer 2 first."
        )

    df = pd.DataFrame(rows)
    df["date"]         = pd.to_datetime(df["date"]).dt.date
    df["daily_return"] = pd.to_numeric(df["daily_return"], errors="coerce")

    # Apply lookback filter (no look-ahead: only past/current data)
    if lookback_days is not None:
        max_date = df["date"].max()
        cutoff   = pd.Timestamp(max_date) - pd.Timedelta(days=lookback_days)
        df = df[df["date"] >= cutoff.date()]

    return df[["asset_id", "date", "daily_return"]].dropna(subset=["daily_return"])


# ---------------------------------------------------------------------------
# Step 3 – prepare_return_matrix
# ---------------------------------------------------------------------------


def prepare_return_matrix(
    returns_df: pd.DataFrame,
    assets_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Build a wide-format daily-return matrix aligned on common trading dates.

    Rules
    -----
    • Only dates where ALL assets have a return are kept (intersection).
      This respects different trading calendars without inventing data.
    • NaN returns are dropped, not filled.

    Returns
    -------
    ret_matrix : DataFrame with DatetimeIndex, one column per symbol
    symbols    : ordered list of asset symbols (same order as ret_matrix cols)
    """
    # Merge symbol names
    merged = returns_df.merge(
        assets_df[["asset_id", "symbol"]], on="asset_id", how="left"
    )

    # Pivot to wide format: date × symbol
    wide = merged.pivot_table(
        index="date", columns="symbol", values="daily_return", aggfunc="first"
    )

    # Keep only dates where ALL assets have data
    wide = wide.dropna(how="any")

    if wide.empty:
        raise ValueError(
            "No common trading dates found across all assets. "
            "Check that Layer 2 has been run for all assets."
        )

    wide = wide.sort_index()
    symbols = list(wide.columns)
    return wide, symbols


# ---------------------------------------------------------------------------
# Step 4 – calculate_statistics
# ---------------------------------------------------------------------------


def calculate_statistics(
    ret_matrix: pd.DataFrame,
    risk_free_rate: float,
) -> dict[str, Any]:
    """
    Compute per-asset expected return, volatility, and Sharpe ratio.

    Formulae (identical to Layer 2)
    --------------------------------
    mu_i     = mean(daily_return_i) * 252
    sigma_i  = std(daily_return_i)  * sqrt(252)
    sharpe_i = (mu_i - rf) / sigma_i
    """
    stats: dict[str, dict] = {}
    for sym in ret_matrix.columns:
        rets = ret_matrix[sym].dropna()
        mu  = float(rets.mean() * ANNUALIZATION_FACTOR)
        vol = float(rets.std() * np.sqrt(ANNUALIZATION_FACTOR))
        sharpe = (mu - risk_free_rate) / vol if vol > 0 else None
        stats[sym] = {"mu": mu, "vol": vol, "sharpe": sharpe}

    return stats


# ---------------------------------------------------------------------------
# Step 5 – calculate_covariance
# ---------------------------------------------------------------------------


def calculate_covariance(ret_matrix: pd.DataFrame) -> np.ndarray:
    """
    Compute the annualized covariance matrix from the aligned return matrix.

    Sigma = cov(daily_returns) * 252

    The result is an N×N symmetric positive-semidefinite matrix where N is
    the number of assets. This is passed directly to the scipy optimizer.
    """
    # pandas .cov() uses unbiased (N-1) denominator
    cov_daily = ret_matrix.cov().values.astype(float)
    return cov_daily * ANNUALIZATION_FACTOR


def calculate_correlation(cov_matrix: np.ndarray) -> np.ndarray:
    """Derive the correlation matrix from the covariance matrix."""
    std = np.sqrt(np.diag(cov_matrix))
    outer_std = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(outer_std > 0, cov_matrix / outer_std, 0.0)
    return corr


# ---------------------------------------------------------------------------
# Step 6 – calculate_portfolio_metrics
# ---------------------------------------------------------------------------


def calculate_portfolio_metrics(
    weights: np.ndarray,
    mu: np.ndarray,
    cov: np.ndarray,
    risk_free_rate: float,
) -> dict[str, float]:
    """
    Compute expected return, volatility, and Sharpe for a weight vector.

    Portfolio return    = w.T @ mu
    Portfolio variance  = w.T @ Sigma @ w
    Portfolio volatility = sqrt(variance)
    Sharpe              = (return - rf) / volatility

    Parameters
    ----------
    weights : (N,) array of portfolio weights (should sum to 1)
    mu      : (N,) array of annualized expected returns
    cov     : (N, N) annualized covariance matrix
    """
    port_return = float(weights @ mu)
    port_var    = float(weights @ cov @ weights)
    port_vol    = float(np.sqrt(max(port_var, 0.0)))  # guard tiny negatives
    sharpe      = (port_return - risk_free_rate) / port_vol if port_vol > 1e-10 else None

    return {
        "portfolio_return":     port_return,
        "portfolio_volatility": port_vol,
        "sharpe_ratio":         sharpe,
    }


# ---------------------------------------------------------------------------
# Step 7 – Optimization objectives
# ---------------------------------------------------------------------------


def _solve(
    objective_fn,
    n_assets: int,
    constraints: list[dict],
    bounds: list[tuple[float, float]],
    n_restarts: int = 5,
) -> OptimizeResult:
    """
    Run scipy.optimize.minimize with multiple random starting points and
    return the result with the lowest objective value (most successful).

    Using multiple restarts reduces sensitivity to the initial guess for
    non-convex objectives such as Maximum Sharpe.
    """
    best: OptimizeResult | None = None
    rng = np.random.default_rng(seed=42)  # deterministic restarts

    for _ in range(n_restarts):
        # Random weight initialisation on the unit simplex
        w0 = rng.dirichlet(np.ones(n_assets))
        result = minimize(
            objective_fn,
            x0=w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 2000},
        )
        if best is None or (result.success and result.fun < best.fun):
            best = result

    return best  # type: ignore[return-value]


def optimize_minimum_volatility(
    mu: np.ndarray,
    cov: np.ndarray,
) -> tuple[np.ndarray, OptimizeResult]:
    """
    Minimize portfolio variance:  w.T @ Sigma @ w
    subject to: sum(w) = 1, 0 <= w_i <= 1
    """
    n = len(mu)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds      = [(0.0, 1.0)] * n

    # Objective: portfolio variance (monotone proxy for volatility)
    def objective(w: np.ndarray) -> float:
        return float(w @ cov @ w)

    result = _solve(objective, n, constraints, bounds)
    return np.clip(result.x, 0, 1), result


def optimize_maximum_sharpe(
    mu: np.ndarray,
    cov: np.ndarray,
    risk_free_rate: float,
) -> tuple[np.ndarray, OptimizeResult]:
    """
    Maximize (w.T @ mu - rf) / sqrt(w.T @ Sigma @ w)
    by minimizing the negative Sharpe ratio.
    subject to: sum(w) = 1, 0 <= w_i <= 1
    """
    n = len(mu)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds      = [(0.0, 1.0)] * n

    def objective(w: np.ndarray) -> float:
        ret = float(w @ mu)
        var = float(w @ cov @ w)
        vol = np.sqrt(max(var, 1e-18))
        return -(ret - risk_free_rate) / vol  # negative for minimisation

    result = _solve(objective, n, constraints, bounds)
    return np.clip(result.x, 0, 1), result


def optimize_maximum_return(
    mu: np.ndarray,
    cov: np.ndarray,
) -> tuple[np.ndarray, OptimizeResult]:
    """
    Maximize w.T @ mu (minimize negative return).
    subject to: sum(w) = 1, 0 <= w_i <= 1

    Note: for unconstrained assets this always concentrates 100% in the
    highest-return asset. Included as a theoretical reference point.
    """
    n = len(mu)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds      = [(0.0, 1.0)] * n

    def objective(w: np.ndarray) -> float:
        return -float(w @ mu)  # negative for minimisation

    result = _solve(objective, n, constraints, bounds)
    return np.clip(result.x, 0, 1), result


def optimize_target_return(
    mu: np.ndarray,
    cov: np.ndarray,
    target_return: float,
) -> tuple[np.ndarray, OptimizeResult]:
    """
    Minimize portfolio volatility subject to a minimum expected return.

    minimize  sqrt(w.T @ Sigma @ w)
    subject to:
        w.T @ mu >= target_return
        sum(w) = 1
        0 <= w_i <= 1

    If the target return exceeds the maximum achievable (100% in the
    best single asset), the constraint is relaxed to the maximum possible.
    """
    n = len(mu)
    max_achievable = float(np.max(mu))
    effective_target = min(target_return, max_achievable)

    if effective_target < target_return:
        print(
            f"  [WARNING] Target return {target_return:.2%} exceeds maximum achievable "
            f"{max_achievable:.2%}. Relaxing to {effective_target:.2%}."
        )

    constraints = [
        {"type": "eq",  "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: float(w @ mu) - effective_target},
    ]
    bounds = [(0.0, 1.0)] * n

    def objective(w: np.ndarray) -> float:
        return float(w @ cov @ w)  # minimize variance (monotone for volatility)

    result = _solve(objective, n, constraints, bounds)
    return np.clip(result.x, 0, 1), result


# ---------------------------------------------------------------------------
# Step 8 – discretize_weights
# ---------------------------------------------------------------------------


def discretize_weights(
    weights: np.ndarray,
    step: float,
) -> np.ndarray:
    """
    Round continuous weights to the nearest multiple of `step`
    while guaranteeing that the discrete weights sum to exactly 1.

    Algorithm
    ---------
    1. Round each weight to the nearest step.
    2. Compute residual = 1 - sum(rounded).
    3. Distribute residual by greedily adjusting the asset whose
       rounded weight has the largest rounding error (fractional part
       closest to 0.5).

    The result is deterministic and satisfies:
      sum(discrete_weights) == 1.0
      all(w >= 0 for w in discrete_weights)
      all(w % step ≈ 0 for w in discrete_weights)

    Parameters
    ----------
    weights : (N,) continuous weight vector
    step    : allocation step (e.g. 0.10 for 10% slots)

    Returns
    -------
    (N,) discrete weight vector
    """
    if not (0.0 < step <= 1.0):
        raise ValueError(f"allocation_step must be in (0, 1], got {step}")

    n_slots = round(1.0 / step)
    # Express weights as slot counts, round, then convert back
    slot_counts = np.array([round(w / step) for w in weights], dtype=float)
    residual    = n_slots - int(slot_counts.sum())

    if residual != 0:
        # Sort by rounding error (descending) to distribute residual
        remainders = (weights / step) - np.floor(weights / step)
        if residual > 0:
            # Add slots to assets with largest fractional parts
            order = np.argsort(-remainders)
        else:
            # Remove slots from assets with smallest fractional parts
            order = np.argsort(remainders)
        for i in range(abs(residual)):
            slot_counts[order[i]] += np.sign(residual)

    discrete = slot_counts * step
    discrete = np.clip(discrete, 0.0, 1.0)
    return discrete


# ---------------------------------------------------------------------------
# Step 9 – calculate_reference_portfolios
# ---------------------------------------------------------------------------


def calculate_reference_portfolios(
    symbols: list[str],
    mu: np.ndarray,
    cov: np.ndarray,
    risk_free_rate: float,
) -> list[dict[str, Any]]:
    """
    Compute metrics for reference (non-optimized) portfolios:
      • Equal-weight: 1/N allocation
      • Single-asset: 100% in each individual asset

    Returns a list of portfolio dicts suitable for printing and storage.
    """
    n = len(symbols)
    refs: list[dict] = []

    # Equal-weight
    eq_w = np.ones(n) / n
    m    = calculate_portfolio_metrics(eq_w, mu, cov, risk_free_rate)
    refs.append({
        "label":    "Equal Weight",
        "type":     "EQUAL_WEIGHT",
        "single":   None,
        "weights":  eq_w,
        **m,
    })

    # Single-asset portfolios
    for i, sym in enumerate(symbols):
        w = np.zeros(n)
        w[i] = 1.0
        m = calculate_portfolio_metrics(w, mu, cov, risk_free_rate)
        refs.append({
            "label":   f"100% {sym}",
            "type":    "SINGLE_ASSET",
            "single":  sym,
            "weights": w,
            **m,
        })

    return refs


# ---------------------------------------------------------------------------
# Step 10 – validate_results
# ---------------------------------------------------------------------------


def validate_results(
    symbols: list[str],
    mu: np.ndarray,
    cov: np.ndarray,
    ret_matrix: pd.DataFrame,
    opt_results: list[dict],
    allocation_step: float,
) -> None:
    """
    Run all 15 validation checks. Raises ValueError on the first failure.

    1.  At least 2 assets available.
    2.  Required assets listed.
    3.  Return data available (non-empty matrix).
    4.  Dates are sorted.
    5.  No NaN in optimization inputs (mu, cov).
    6.  Covariance matrix dimensions correct.
    7.  Covariance matrix is finite.
    8.  Continuous weights sum ≈ 1.
    9.  Continuous weights in [0, 1].
    10. Discrete weights are multiples of allocation_step.
    11. Discrete weights sum to 1.
    12. Portfolio volatility >= 0.
    13. Sharpe is finite when vol > 0.
    14. Optimizer reported success.
    15. No future data: data_end <= today.
    """
    n = len(symbols)

    # 1 – At least 2 assets
    if n < 2:
        raise ValueError(f"Validation [1] FAILED: need >= 2 assets, got {n}.")

    # 2 – Assets present
    if not symbols:
        raise ValueError("Validation [2] FAILED: no symbols found.")

    # 3 – Return data available
    if ret_matrix.empty or len(ret_matrix) < 2:
        raise ValueError("Validation [3] FAILED: return matrix is empty or has < 2 rows.")

    # 4 – Dates sorted
    idx = list(ret_matrix.index)
    if idx != sorted(idx):
        raise ValueError("Validation [4] FAILED: return matrix dates are not sorted.")

    # 5 – No NaN in optimization inputs
    if np.any(np.isnan(mu)):
        raise ValueError("Validation [5] FAILED: NaN in expected return vector mu.")
    if np.any(np.isnan(cov)):
        raise ValueError("Validation [5] FAILED: NaN in covariance matrix.")

    # 6 – Covariance dimensions
    if cov.shape != (n, n):
        raise ValueError(
            f"Validation [6] FAILED: covariance shape {cov.shape} != ({n},{n})."
        )

    # 7 – Covariance finite
    if not np.all(np.isfinite(cov)):
        raise ValueError("Validation [7] FAILED: covariance matrix contains inf/NaN.")

    for r in opt_results:
        cw = r["continuous_weights"]
        dw = r["discrete_weights"]
        obj = r["objective"]

        # 8 – Continuous weights sum ≈ 1
        s = float(np.sum(cw))
        if abs(s - 1.0) > 1e-4:
            raise ValueError(
                f"Validation [8] FAILED [{obj}]: continuous weights sum = {s:.6f} (expected 1)."
            )

        # 9 – Continuous weights in [0, 1]
        if np.any(cw < -1e-6) or np.any(cw > 1.0 + 1e-6):
            raise ValueError(
                f"Validation [9] FAILED [{obj}]: continuous weight outside [0,1]: {cw}."
            )

        # 10 – Discrete weights are multiples of step
        tol = allocation_step * 1e-6
        for w in dw:
            rem = abs(round(w / allocation_step) * allocation_step - w)
            if rem > tol:
                raise ValueError(
                    f"Validation [10] FAILED [{obj}]: discrete weight {w} is not a "
                    f"multiple of {allocation_step}."
                )

        # 11 – Discrete weights sum to 1
        ds = float(np.sum(dw))
        if abs(ds - 1.0) > 1e-6:
            raise ValueError(
                f"Validation [11] FAILED [{obj}]: discrete weights sum = {ds:.6f}."
            )

        # 12 – Portfolio volatility >= 0
        if r["portfolio_volatility"] < 0:
            raise ValueError(
                f"Validation [12] FAILED [{obj}]: negative portfolio volatility."
            )

        # 13 – Sharpe finite when vol > 0
        if r["portfolio_volatility"] > 1e-10 and r["sharpe_ratio"] is not None:
            if not np.isfinite(r["sharpe_ratio"]):
                raise ValueError(
                    f"Validation [13] FAILED [{obj}]: non-finite Sharpe ratio."
                )

        # 14 – Optimizer success
        if not r.get("solver_success", True):
            print(
                f"  [WARNING] Validation [14]: solver did not converge for {obj}. "
                "Results may be suboptimal."
            )

    # 15 – No future data
    max_date = max(ret_matrix.index)
    today    = date.today()
    if max_date > today:
        raise ValueError(
            f"Validation [15] FAILED: data_end {max_date} is in the future."
        )


# ---------------------------------------------------------------------------
# Step 11 – Supabase save functions
# ---------------------------------------------------------------------------


def _upsert(client: Client, table: str, record: dict | list[dict]) -> None:
    data = record if isinstance(record, list) else [record]
    for i in range(0, len(data), 300):
        client.table(table).upsert(data[i : i + 300]).execute()


def save_optimization_run(
    client: Client,
    objective: str,
    config: dict,
    data_start: date,
    data_end: date,
    batch_id: str,
) -> str:
    """Insert a new optimization run with status=RUNNING. Returns run UUID."""
    record = {
        "batch_id":        batch_id,
        "objective":       objective,
        "initial_capital": config["initial_capital"],
        "risk_free_rate":  config["risk_free_rate"],
        "lookback_days":   config.get("lookback_days"),
        "data_start_date": str(data_start),
        "data_end_date":   str(data_end),
        "allocation_step": config["allocation_step"],
        "target_return":   config.get("target_return"),
        "constraints":     {"no_short_selling": True, "weight_sum": 1.0},
        "status":          "RUNNING",
    }
    result = client.table("portfolio_optimization_runs").insert(record).execute()
    return result.data[0]["id"]


def _complete_run(
    client: Client, run_id: str, success: bool, error: str = ""
) -> None:
    update = {
        "status":       "SUCCESS" if success else "FAILED",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not success and error:
        update["error_message"] = error[:2000]
    client.table("portfolio_optimization_runs").update(update).eq("id", run_id).execute()


def save_allocations(
    client: Client,
    run_id: str,
    symbols: list[str],
    assets_df: pd.DataFrame,
    continuous_weights: np.ndarray,
    discrete_weights: np.ndarray,
    per_asset_stats: dict[str, dict],
    cov: np.ndarray,
    port_vol: float,
) -> None:
    """Upsert one portfolio_allocations row per asset."""
    sym_to_id = dict(zip(assets_df["symbol"], assets_df["asset_id"]))

    records = []
    for i, sym in enumerate(symbols):
        cw = float(continuous_weights[i])
        dw = float(discrete_weights[i])

        # Marginal volatility contribution: w_i * (Sigma @ w)_i / sigma_p
        if port_vol > 1e-10:
            sigma_w = cov @ continuous_weights
            vol_contrib = float(continuous_weights[i] * sigma_w[i] / port_vol)
        else:
            vol_contrib = None

        records.append({
            "run_id":                run_id,
            "asset_id":              sym_to_id.get(sym),
            "asset_symbol":          sym,
            "continuous_weight":     cw,
            "discrete_weight":       dw,
            "expected_return":       per_asset_stats[sym]["mu"],
            "expected_volatility":   per_asset_stats[sym]["vol"],
            "volatility_contribution": vol_contrib,
        })

    _upsert(client, "portfolio_allocations", records)


def save_portfolio_result(
    client: Client,
    run_id: str,
    portfolio_type: str,
    single_asset_symbol: str | None,
    metrics: dict,
    initial_capital: float,
) -> None:
    """Upsert one portfolio_results row."""
    exp_final = (
        initial_capital * (1.0 + metrics["portfolio_return"])
        if metrics.get("portfolio_return") is not None else None
    )
    record = {
        "run_id":              run_id,
        "portfolio_type":      portfolio_type,
        "single_asset_symbol": single_asset_symbol,
        "portfolio_return":    metrics.get("portfolio_return"),
        "portfolio_volatility": metrics.get("portfolio_volatility"),
        "sharpe_ratio":        metrics.get("sharpe_ratio"),
        "expected_final_value": exp_final,
    }
    _upsert(client, "portfolio_results", record)


def save_covariance_inputs(
    client: Client,
    run_id: str,
    symbols: list[str],
    cov: np.ndarray,
    corr: np.ndarray,
) -> None:
    """Upsert full covariance and correlation matrices for reproducibility."""
    n = len(symbols)
    records = []
    for i in range(n):
        for j in range(n):
            records.append({
                "run_id":         run_id,
                "asset_1_symbol": symbols[i],
                "asset_2_symbol": symbols[j],
                "covariance":     float(cov[i, j]),
                "correlation":    float(corr[i, j]),
            })
    _upsert(client, "portfolio_covariance_inputs", records)


def save_results(
    client: Client,
    run_id: str,
    objective: str,
    symbols: list[str],
    assets_df: pd.DataFrame,
    continuous_weights: np.ndarray,
    discrete_weights: np.ndarray,
    per_asset_stats: dict[str, dict],
    cov: np.ndarray,
    corr: np.ndarray,
    metrics: dict,
    initial_capital: float,
) -> None:
    """Persist all Layer 6 results for one optimization objective."""
    # Asset allocations
    save_allocations(
        client, run_id, symbols, assets_df,
        continuous_weights, discrete_weights,
        per_asset_stats, cov, metrics["portfolio_volatility"],
    )

    # Portfolio-level result
    save_portfolio_result(
        client, run_id, "OPTIMIZED", None, metrics, initial_capital
    )

    # Mark run as successful
    _complete_run(client, run_id, success=True)


# ---------------------------------------------------------------------------
# Step 12 – print_report
# ---------------------------------------------------------------------------


def print_report(
    symbols: list[str],
    per_asset_stats: dict[str, dict],
    cov: np.ndarray,
    corr: np.ndarray,
    ret_matrix: pd.DataFrame,
    opt_results: list[dict],
    ref_portfolios: list[dict],
    config: dict,
) -> None:
    """Print the full Layer 6 console report."""
    n = len(symbols)
    w_col = 8
    rf    = config["risk_free_rate"]
    step  = config["allocation_step"]

    def pct(v, decimals=2):
        return f"{v * 100:.{decimals}f}%" if v is not None else "N/A"

    print()
    print("=" * 50)
    print("LAYER 6 — PORTFOLIO OPTIMIZATION")
    print("=" * 50)
    print()
    print("Assets:")
    for s in symbols:
        print(f"  {s}")
    print()
    print("Lookback:")
    data_start = str(min(ret_matrix.index))
    data_end   = str(max(ret_matrix.index))
    print(f"  {data_start} to {data_end}  ({len(ret_matrix):,} common trading days)")
    print()
    print(f"Risk-Free Rate:  {pct(rf)}")
    print(f"Initial Capital: ${config['initial_capital']:,.2f}")
    print()

    # ── Input statistics ─────────────────────────────────────────────────
    print("=" * 50)
    print("INPUT STATISTICS")
    print("=" * 50)
    print(f"  {'Asset':<8}  {'Return':>10}  {'Volatility':>12}  {'Sharpe':>8}")
    print("  " + "-" * 44)
    for sym in symbols:
        s = per_asset_stats[sym]
        sh = f"{s['sharpe']:.4f}" if s['sharpe'] is not None else "N/A"
        print(f"  {sym:<8}  {pct(s['mu']):>10}  {pct(s['vol']):>12}  {sh:>8}")
    print()

    # ── Correlation matrix ───────────────────────────────────────────────
    print("=" * 50)
    print("CORRELATION MATRIX")
    print("=" * 50)
    header = "  " + " " * 10 + "".join(f"{s:>{w_col}}" for s in symbols)
    print(header)
    for i, si in enumerate(symbols):
        row = f"  {si:<10}" + "".join(f"{corr[i, j]:>{w_col}.4f}" for j in range(n))
        print(row)
    print()

    # ── Covariance matrix ────────────────────────────────────────────────
    print("COVARIANCE MATRIX  (annualized)")
    print(f"  {'Asset':<10}" + "".join(f"{s:>{w_col}}" for s in symbols))
    for i, si in enumerate(symbols):
        row = f"  {si:<10}" + "".join(f"{cov[i, j]:>{w_col}.5f}" for j in range(n))
        print(row)
    print()

    # ── Optimization results ─────────────────────────────────────────────
    print("=" * 50)
    print("OPTIMIZATION RESULTS")
    print("=" * 50)
    for r in opt_results:
        print()
        print(f"  Objective: {r['objective']}")
        if r["objective"] == OBJ_TARGET_RETURN:
            print(f"  Target Return: {pct(config.get('target_return', 0))}")
        print()
        for i, sym in enumerate(symbols):
            print(f"    {sym:<8}  {pct(r['continuous_weights'][i]):>8}")
        print()
        print(f"    Expected Return    : {pct(r['portfolio_return'])}")
        print(f"    Expected Volatility: {pct(r['portfolio_volatility'])}")
        sh = f"{r['sharpe_ratio']:.4f}" if r['sharpe_ratio'] is not None else "N/A"
        print(f"    Sharpe Ratio       : {sh}")
        exp_val = config["initial_capital"] * (1 + r["portfolio_return"])
        print(f"    Expected Value*    : ${exp_val:,.2f}")
        if not r.get("solver_success", True):
            print(f"    [WARNING] Solver did not converge cleanly.")
        print("  " + "-" * 46)

    print()
    print("  *Expected Value = Initial Capital × (1 + Expected Return)")
    print("   This is a HISTORICAL ESTIMATE, not a forecast of future returns.")
    print()

    # ── Reference portfolios ─────────────────────────────────────────────
    print("=" * 50)
    print("REFERENCE PORTFOLIOS")
    print("=" * 50)
    for ref in ref_portfolios:
        print()
        print(f"  {ref['label']}")
        for i, sym in enumerate(symbols):
            print(f"    {sym:<8}  {pct(ref['weights'][i]):>8}")
        print(f"    Expected Return    : {pct(ref['portfolio_return'])}")
        print(f"    Expected Volatility: {pct(ref['portfolio_volatility'])}")
        sh = f"{ref['sharpe_ratio']:.4f}" if ref['sharpe_ratio'] is not None else "N/A"
        print(f"    Sharpe Ratio       : {sh}")
    print()

    # ── Discrete allocation ──────────────────────────────────────────────
    print("=" * 50)
    print("DISCRETE ALLOCATION")
    print("=" * 50)
    print(f"  Allocation Step: {pct(step)}")
    print()
    # Show discrete for each objective
    for r in opt_results:
        print(f"  Objective: {r['objective']}")
        print(f"    {'Asset':<8}  {'Continuous':>12}  {'Discrete':>10}")
        print("    " + "-" * 34)
        for i, sym in enumerate(symbols):
            print(
                f"    {sym:<8}  {pct(r['continuous_weights'][i]):>12}  "
                f"{pct(r['discrete_weights'][i]):>10}"
            )
        ds = sum(r["discrete_weights"])
        status = "PASSED" if abs(ds - 1.0) < 1e-6 else "FAILED"
        print(f"    Discrete sum: {ds:.4f}  =>  Validation: {status}")
        print()

    print()
    print("=" * 50)
    print("LAYER 6 COMPLETE")
    print("=" * 50)
    print()
    print("  Layer 7 inputs available:")
    print(f"    Assets:          {symbols}")
    print(f"    Allocation step: {step}")
    print(f"    Cov matrix:      {n}×{n}  (stored in portfolio_covariance_inputs)")
    print(f"    Discrete weights: stored in portfolio_allocations")
    print()
    print("  DISCLAIMER: All statistics are based on historical data.")
    print("  No portfolio is declared 'best'. Results are objective-specific.")
    print("=" * 50)


# ---------------------------------------------------------------------------
# Orchestrator – main
# ---------------------------------------------------------------------------


def main(batch_id: str | None = None) -> None:
    """
    Full Layer 6 pipeline.

    Flow
    ----
    load_assets + load_market_returns
      → prepare_return_matrix
      → calculate_statistics
      → calculate_covariance / correlation
      → [for each objective] optimize → validate → save
      → reference portfolios
      → print_report
    """
    config = get_config()
    client = get_client(config)

    if batch_id is None:
        batch_id = input("Enter batch_id: ").strip()

    print("=" * 50)
    print("LAYER 6 — PORTFOLIO OPTIMIZATION")
    print("=" * 50)
    print(f"  Batch: {batch_id}")
    print()

    # -- Load data (batch-scoped) -------------------------------------------
    print("Loading data from Supabase...")
    assets_df   = load_assets(client)
    returns_df  = load_market_returns(client, config.get("lookback_days"), batch_id)
    print(f"  {len(assets_df)} assets,  {len(returns_df):,} indicator rows loaded.")

    # ── Prepare aligned return matrix ──────────────────────────────────────
    print("Preparing aligned return matrix...")
    ret_matrix, symbols = prepare_return_matrix(returns_df, assets_df)
    n = len(symbols)
    print(
        f"  {n} assets × {len(ret_matrix):,} common trading days  "
        f"({str(min(ret_matrix.index))} to {str(max(ret_matrix.index))})"
    )

    # ── Compute statistics ─────────────────────────────────────────────────
    print("Computing statistics and covariance...")
    per_asset_stats = calculate_statistics(ret_matrix, config["risk_free_rate"])
    cov  = calculate_covariance(ret_matrix)
    corr = calculate_correlation(cov)

    # mu vector aligned with symbols order
    mu = np.array([per_asset_stats[s]["mu"] for s in symbols])

    # ── Run optimization objectives ─────────────────────────────────────────
    print("Running classical portfolio optimization...")

    default_target = config.get("target_return") or float(np.mean(mu))

    optimization_specs = [
        (OBJ_MIN_VOL,       lambda: optimize_minimum_volatility(mu, cov)),
        (OBJ_MAX_SHARPE,    lambda: optimize_maximum_sharpe(mu, cov, config["risk_free_rate"])),
        (OBJ_MAX_RETURN,    lambda: optimize_maximum_return(mu, cov)),
        (OBJ_TARGET_RETURN, lambda: optimize_target_return(mu, cov, default_target)),
    ]

    opt_results  : list[dict] = []
    saved_run_ids: dict[str, str] = {}

    data_start = min(ret_matrix.index)
    data_end   = max(ret_matrix.index)

    for objective, opt_fn in optimization_specs:
        print(f"  [{objective}]")

        cw, result = opt_fn()
        # Normalize to ensure exact sum = 1 after scipy rounding
        cw = cw / cw.sum() if cw.sum() > 1e-10 else cw
        dw = discretize_weights(cw, config["allocation_step"])
        m  = calculate_portfolio_metrics(cw, mu, cov, config["risk_free_rate"])

        opt_results.append({
            "objective":          objective,
            "continuous_weights": cw,
            "discrete_weights":   dw,
            "solver_success":     result.success,
            **m,
        })

        # Save to Supabase
        run_id = save_optimization_run(client, objective, config, data_start, data_end, batch_id)
        saved_run_ids[objective] = run_id

        save_results(
            client, run_id, objective,
            symbols, assets_df,
            cw, dw,
            per_asset_stats, cov, corr, m,
            config["initial_capital"],
        )

        # Save covariance inputs once per run (for Layer 7 reproducibility)
        save_covariance_inputs(client, run_id, symbols, cov, corr)

    # ── Reference portfolios ────────────────────────────────────────────────
    print("Computing reference portfolios...")
    ref_portfolios = calculate_reference_portfolios(
        symbols, mu, cov, config["risk_free_rate"]
    )

    # Save reference portfolios using the MIN_VOL run_id as parent
    parent_run_id = saved_run_ids[OBJ_MIN_VOL]
    for ref in ref_portfolios:
        save_portfolio_result(
            client, parent_run_id,
            ref["type"], ref.get("single"),
            ref, config["initial_capital"],
        )

    # ── Validate ────────────────────────────────────────────────────────────
    print("Validating results...")
    validate_results(
        symbols, mu, cov, ret_matrix,
        opt_results, config["allocation_step"],
    )
    print("  All validation checks passed.")

    # ── Print report ────────────────────────────────────────────────────────
    print_report(
        symbols, per_asset_stats, cov, corr,
        ret_matrix, opt_results, ref_portfolios, config,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    _bid = sys.argv[1] if len(sys.argv) > 1 else None
    main(_bid)
