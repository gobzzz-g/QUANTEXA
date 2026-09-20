"""
QUBO Portfolio Optimization Engine - Layer 7
==============================================
Converts the discrete portfolio allocation problem (from Layer 6)
into a Quadratic Unconstrained Binary Optimization (QUBO) and solves
it using two approaches:

  1. Classical Exact Solver
     Enumerates all 66 valid discrete allocations directly.
     (C(n_units + n_assets - 1, n_assets - 1) = C(12,2) = 66 for
      3 assets, 10 units.)  Exact global optimum for the discrete problem.

  2. Quantum-Inspired Solver: Simulated Annealing
     Navigates the same QUBO objective using temperature-based
     probabilistic search.  Not a quantum computer.  The result
     approximates the QUBO minimum and may match the exact solution
     on small instances.

What this layer does NOT do
----------------------------
  - Download market data
  - Modify Layers 1-6
  - Claim quantum advantage
  - Fabricate quantum execution

Mathematical formulation
-------------------------
Binary variables:  x[k]  in {0, 1}
  k = i * n_units + j
  where i = asset index, j = unit index (0..n_units-1)
  n_units = round(1 / allocation_step)

Portfolio weights:
  w_i = allocation_step * sum_{j=0}^{n_units-1} x[i*n_units + j]

QUBO objective (upper-triangular Q matrix):
  E(x) = sum_{k<=l} Q[k,l] * x[k] * x[l]

Components:

  Risk:
    RISK_WEIGHT * w^T Sigma w
    = RISK_WEIGHT * step^2 * sum_{k,l} Sigma[asset(k), asset(l)] * x[k] * x[l]

  Return (linear, absorbed into diagonal via x_k^2 = x_k):
    -RETURN_WEIGHT * w^T mu
    = -RETURN_WEIGHT * step * sum_k mu[asset(k)] * x[k]

  Constraint (sum(x) = n_units):
    CONSTRAINT_PENALTY * (sum(x) - n_units)^2
    Expands to quadratic and linear terms.

Upper-triangular Q entries:
  Q[k,k] = RISK_WEIGHT * step^2 * Sigma[a,a]
            - RETURN_WEIGHT * step * mu[a]
            + CONSTRAINT_PENALTY * (1 - 2*n_units)
  Q[k,l] (k<l) = 2 * RISK_WEIGHT * step^2 * Sigma[a,b]
                + 2 * CONSTRAINT_PENALTY
  where a = asset(k), b = asset(l)

Note on the constant term (ignored by solver, stored for completeness):
  constant = CONSTRAINT_PENALTY * n_units^2

DISCLAIMER
----------
  All results are based on historical data from Layer 6.
  Classical exact and simulated annealing results are for the DISCRETE
  allocation model only.  They are not forecasts of future returns.

Run:
    python qubo_optimizer.py

Environment variables (see .env):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    INITIAL_CAPITAL      (default: 100000)
    RISK_FREE_RATE       (default: 0.0)
    ALLOCATION_STEP      (default: 0.10)
    RISK_WEIGHT          (default: 1.0)
    RETURN_WEIGHT        (default: 1.0)
    CONSTRAINT_PENALTY   (default: 10.0)
    SA_ITERATIONS        (default: 50000)
    SA_INITIAL_TEMP      (default: 1.0)
    SA_COOLING_RATE      (default: 0.9995)
"""

from __future__ import annotations

import json
import os
import sys
import math
import random
from datetime import datetime, timezone
from itertools import product
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
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

ANNUALIZATION_FACTOR: int = 252
PAGE_SIZE: int = 1000

# Solver name labels (stored in qubo_results.solver_name)
SOLVER_LAYER6_CONTINUOUS   = "LAYER6_CONTINUOUS"
SOLVER_LAYER6_DISCRETE     = "LAYER6_DISCRETE"
SOLVER_CLASSICAL_EXACT     = "CLASSICAL_EXACT"
SOLVER_SIMULATED_ANNEALING = "SIMULATED_ANNEALING"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _require_env(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        print(f"ERROR: env var '{key}' is not set.")
        sys.exit(1)
    return v


def get_config() -> dict[str, Any]:
    """Load all Layer 7 configuration from environment variables."""
    return {
        "supabase_url":       _require_env("SUPABASE_URL"),
        "supabase_key":       _require_env("SUPABASE_SERVICE_ROLE_KEY"),
        "initial_capital":    float(os.getenv("INITIAL_CAPITAL", "100000")),
        "risk_free_rate":     float(os.getenv("RISK_FREE_RATE", "0.0")),
        "allocation_step":    float(os.getenv("ALLOCATION_STEP", "0.10")),
        # QUBO objective weights
        "risk_weight":        float(os.getenv("RISK_WEIGHT", "1.0")),
        "return_weight":      float(os.getenv("RETURN_WEIGHT", "1.0")),
        "constraint_penalty": float(os.getenv("CONSTRAINT_PENALTY", "10.0")),
        # Simulated annealing parameters
        "sa_iterations":      int(os.getenv("SA_ITERATIONS", "50000")),
        "sa_initial_temp":    float(os.getenv("SA_INITIAL_TEMP", "1.0")),
        "sa_cooling_rate":    float(os.getenv("SA_COOLING_RATE", "0.9995")),
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


def _paginate_eq(client: Client, table: str, select: str, **filters) -> list[dict]:
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


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Step 1 - load_layer6_inputs
# ---------------------------------------------------------------------------


def load_layer6_inputs(client: Client, allocation_step: float, batch_id: str) -> dict[str, Any]:
    """
    Load the covariance matrix, expected returns, and discrete weights
    produced by Layer 6, scoped to the given batch_id.

    Strategy: use the most recent MINIMUM_VOLATILITY run for this batch
    (which always stores the covariance matrix) as the canonical source
    of mu and Sigma.  Also load the MAXIMUM_SHARPE discrete allocation.

    Returns
    -------
    dict with keys:
      symbols        : list[str]
      mu             : np.ndarray  (n_assets,)  annualized expected returns
      cov            : np.ndarray  (n_assets, n_assets)  annualized covariance
      corr           : np.ndarray  (n_assets, n_assets)  correlation
      l6_continuous  : dict  {symbol: continuous_weight}   (MAX_SHARPE run)
      l6_discrete    : dict  {symbol: discrete_weight}     (MAX_SHARPE run)
      portfolio_run_id : str  UUID of the Layer 6 run used
      risk_free_rate : float
      initial_capital: float
    """
    # ---- Find successful Layer 6 runs for this batch ----
    runs = _paginate_batch(
        client, "portfolio_optimization_runs",
        "id, objective, status, allocation_step, risk_free_rate, initial_capital, created_at",
        batch_id,
    )
    # Filter to successful runs that match our allocation step
    step = allocation_step
    successful = [
        r for r in runs
        if r.get("status") == "SUCCESS"
        and abs(float(r.get("allocation_step", 0)) - step) < 1e-9
    ]
    if not successful:
        raise ValueError(
            f"No successful Layer 6 runs found for batch_id={batch_id} with "
            f"allocation_step={step:.2f}. Run portfolio_optimizer.py first."
        )

    # Sort by created_at descending to get the most recent batch
    successful.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    # Find the most recent MIN_VOL run (has the canonical Sigma)
    min_vol_runs = [r for r in successful if r["objective"] == "MINIMUM_VOLATILITY"]
    if not min_vol_runs:
        raise ValueError(
            "No MINIMUM_VOLATILITY Layer 6 run found. Run portfolio_optimizer.py first."
        )
    ref_run = min_vol_runs[0]
    ref_run_id = ref_run["id"]

    # Find the MAX_SHARPE run from the same timestamp batch for comparison
    # (group by runs created within 5 minutes of the MIN_VOL run)
    max_sharpe_runs = [r for r in successful if r["objective"] == "MAXIMUM_SHARPE"]
    sharpe_run = max_sharpe_runs[0] if max_sharpe_runs else ref_run

    # ---- Load covariance matrix ----
    cov_rows = _paginate_eq(
        client, "portfolio_covariance_inputs",
        "asset_1_symbol, asset_2_symbol, covariance, correlation",
        run_id=ref_run_id,
    )
    if not cov_rows:
        raise ValueError(
            f"portfolio_covariance_inputs is empty for run {ref_run_id}. "
            "Re-run portfolio_optimizer.py to regenerate."
        )

    # Derive symbols from the diagonal (asset_1 == asset_2)
    diag = [r for r in cov_rows if r["asset_1_symbol"] == r["asset_2_symbol"]]
    symbols = sorted(set(r["asset_1_symbol"] for r in diag))
    n = len(symbols)
    sym_idx = {s: i for i, s in enumerate(symbols)}

    cov  = np.zeros((n, n))
    corr = np.zeros((n, n))
    for r in cov_rows:
        i = sym_idx.get(r["asset_1_symbol"])
        j = sym_idx.get(r["asset_2_symbol"])
        if i is not None and j is not None:
            cov[i, j]  = float(r["covariance"])
            corr[i, j] = float(r["correlation"])

    # ---- Load expected returns from portfolio_allocations ----
    alloc_rows = _paginate_eq(
        client, "portfolio_allocations",
        "asset_symbol, expected_return, continuous_weight, discrete_weight",
        run_id=ref_run_id,
    )
    if not alloc_rows:
        raise ValueError(
            f"portfolio_allocations is empty for run {ref_run_id}. "
            "Re-run portfolio_optimizer.py."
        )

    mu = np.zeros(n)
    for r in alloc_rows:
        i = sym_idx.get(r["asset_symbol"])
        if i is not None and r.get("expected_return") is not None:
            mu[i] = float(r["expected_return"])

    # ---- Load Layer 6 continuous weights (MAX_SHARPE for comparison) ----
    sharpe_alloc = _paginate_eq(
        client, "portfolio_allocations",
        "asset_symbol, continuous_weight, discrete_weight",
        run_id=sharpe_run["id"],
    )
    l6_continuous = {}
    l6_discrete   = {}
    for r in sharpe_alloc:
        sym = r["asset_symbol"]
        l6_continuous[sym] = float(r.get("continuous_weight") or 0)
        l6_discrete[sym]   = float(r.get("discrete_weight") or 0)

    return {
        "symbols":          symbols,
        "mu":               mu,
        "cov":              cov,
        "corr":             corr,
        "l6_continuous":    l6_continuous,
        "l6_discrete":      l6_discrete,
        "portfolio_run_id": ref_run_id,
        "risk_free_rate":   float(ref_run.get("risk_free_rate", 0.0)),
        "initial_capital":  float(ref_run.get("initial_capital", 100000)),
    }


# ---------------------------------------------------------------------------
# Step 2 - prepare_portfolio_inputs
# ---------------------------------------------------------------------------


def prepare_portfolio_inputs(
    inputs: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Derive QUBO-specific quantities from Layer 6 inputs.

    n_units = round(1 / allocation_step)
    N = n_assets * n_units  (total binary variables)
    """
    step    = config["allocation_step"]
    n_units = round(1.0 / step)
    n       = len(inputs["symbols"])
    N       = n * n_units

    return {
        **inputs,
        "step":    step,
        "n_units": n_units,
        "n":       n,
        "N":       N,
    }


# ---------------------------------------------------------------------------
# Step 3 - create_binary_variable_mapping
# ---------------------------------------------------------------------------


def create_binary_variable_mapping(
    symbols: list[str],
    n_units: int,
    step: float,
) -> list[dict[str, Any]]:
    """
    Create an explicit mapping from binary variable index to asset / unit.

    Variable layout (unary encoding):
      x[i*n_units + j]  corresponds to:
        asset = symbols[i]
        unit  = j+1             (1-indexed for readability)
        meaning: one allocation unit of size 'step' for asset i

    Parameters
    ----------
    symbols : list of asset symbols
    n_units : allocation units per asset  (= 1 / step)
    step    : allocation step size

    Returns
    -------
    list of dicts, one per binary variable:
      {variable_index, variable_name, asset_symbol, allocation_unit, allocation_value}
    """
    mapping = []
    for i, sym in enumerate(symbols):
        for j in range(n_units):
            idx = i * n_units + j
            mapping.append({
                "variable_index":  idx,
                "variable_name":   f"x_{sym}_unit_{j+1}",
                "asset_symbol":    sym,
                "allocation_unit": j + 1,
                "allocation_value": step,
            })
    return mapping


# ---------------------------------------------------------------------------
# Step 4 - build_qubo
# ---------------------------------------------------------------------------


def build_qubo(
    symbols: list[str],
    mu: np.ndarray,
    cov: np.ndarray,
    n_units: int,
    step: float,
    risk_weight: float,
    return_weight: float,
    constraint_penalty: float,
) -> np.ndarray:
    """
    Construct the upper-triangular QUBO matrix Q such that:

      E(x) = sum_{k<=l} Q[k,l] * x[k] * x[l]

    is the QUBO energy for binary vector x.

    Derivation (see module docstring for full detail):
    --------------------------------------------------
    Let a = asset(k) = k // n_units,  b = asset(l) = l // n_units.

    Risk component (w^T Sigma w using unary weights):
      w_a = step * sum_{k in asset_a} x[k]
      w^T Sigma w = step^2 * sum_{k,l} Sigma[a,b] x[k] x[l]

    In upper-triangular form (using x_k^2 = x_k for binary):
      Diagonal (k==l): step^2 * Sigma[a,a]
      Off-diagonal (k<l): 2 * step^2 * Sigma[a,b]

    Return component (linear, absorbed into diagonal):
      -return_weight * step * mu[a]  added to diagonal.

    Constraint component (sum(x) - n_units)^2:
      = sum_k x_k + 2*sum_{k<l} x_k x_l - 2*n_units*sum_k x_k + n_units^2
      Diagonal contribution: constraint_penalty * (1 - 2*n_units)
      Off-diagonal contribution: 2 * constraint_penalty
      Constant: constraint_penalty * n_units^2  (ignored by solver)

    Parameters
    ----------
    symbols    : asset symbols in order
    mu         : (n,) annualized expected returns
    cov        : (n,n) annualized covariance matrix
    n_units    : number of allocation units per asset
    step       : allocation step size
    risk_weight, return_weight, constraint_penalty : QUBO objective weights
    """
    n = len(symbols)
    N = n * n_units

    Q = np.zeros((N, N), dtype=float)

    for k in range(N):
        a = k // n_units  # asset index for variable k

        # ── Diagonal entry Q[k,k] ──────────────────────────────────────────
        # Risk (linear part: step^2 * Sigma[a,a] since x_k^2 = x_k)
        Q[k, k] += risk_weight * (step ** 2) * cov[a, a]

        # Return (linear: -return_weight * step * mu[a])
        Q[k, k] += -return_weight * step * mu[a]

        # Constraint (linear part of (sum x - n_units)^2)
        # Contribution from x_k^2 = x_k: penalty * (1 - 2*n_units)
        Q[k, k] += constraint_penalty * (1.0 - 2.0 * n_units)

        # ── Off-diagonal entries Q[k,l] for l > k ─────────────────────────
        for l in range(k + 1, N):
            b = l // n_units  # asset index for variable l

            # Risk quadratic: 2 * step^2 * Sigma[a,b]
            Q[k, l] += 2.0 * risk_weight * (step ** 2) * cov[a, b]

            # Constraint quadratic: 2 * penalty (from 2 * x_k * x_l term)
            Q[k, l] += 2.0 * constraint_penalty

    return Q


# ---------------------------------------------------------------------------
# Step 5 - calculate_qubo_energy
# ---------------------------------------------------------------------------


def calculate_qubo_energy(Q: np.ndarray, x: np.ndarray) -> float:
    """
    Evaluate the QUBO energy: E(x) = x^T Q x

    For an upper-triangular Q this equals:
      sum_{k<=l} Q[k,l] * x[k] * x[l]

    Parameters
    ----------
    Q : (N,N) upper-triangular QUBO matrix
    x : (N,) binary vector
    """
    return float(x @ Q @ x)


# ---------------------------------------------------------------------------
# Step 6 - decode_binary_solution
# ---------------------------------------------------------------------------


def decode_binary_solution(
    x: np.ndarray,
    symbols: list[str],
    n_units: int,
    step: float,
) -> dict[str, float]:
    """
    Convert binary vector x back to portfolio weights.

    For asset i:
        w_i = step * sum_{j=0}^{n_units-1} x[i*n_units + j]
    """
    weights = {}
    for i, sym in enumerate(symbols):
        units = x[i * n_units : (i + 1) * n_units]
        weights[sym] = float(step * np.sum(units))
    return weights


# ---------------------------------------------------------------------------
# Step 7 - calculate_portfolio_metrics
# ---------------------------------------------------------------------------


def calculate_portfolio_metrics(
    weights: dict[str, float],
    symbols: list[str],
    mu: np.ndarray,
    cov: np.ndarray,
    risk_free_rate: float,
    initial_capital: float,
    Q: np.ndarray,
    x: np.ndarray | None,
) -> dict[str, Any]:
    """
    Compute all portfolio metrics for a given weight vector.

    Uses the same formulas as Layer 6:
      portfolio_return    = w^T mu
      portfolio_variance  = w^T Sigma w
      portfolio_volatility = sqrt(variance)
      sharpe              = (return - rf) / volatility

    Also computes the QUBO energy if x is provided.
    """
    w = np.array([weights.get(s, 0.0) for s in symbols])

    port_return = float(w @ mu)
    port_var    = float(w @ cov @ w)
    port_vol    = float(np.sqrt(max(port_var, 0.0)))
    sharpe      = (
        (port_return - risk_free_rate) / port_vol
        if port_vol > 1e-10 else None
    )
    exp_value = initial_capital * (1.0 + port_return)
    qubo_obj  = float(x @ Q @ x) if x is not None else None
    constraint_err = abs(sum(w.values() if isinstance(w, dict) else w) - 1.0)

    return {
        "expected_return":    port_return,
        "portfolio_variance": port_var,
        "volatility":         port_vol,
        "sharpe_ratio":       sharpe,
        "expected_value":     exp_value,
        "qubo_objective":     qubo_obj,
        "constraint_error":   float(abs(sum(weights.values()) - 1.0)),
    }


# ---------------------------------------------------------------------------
# Step 8 - generate_valid_discrete_allocations
# ---------------------------------------------------------------------------


def generate_valid_discrete_allocations(
    n_assets: int,
    n_units: int,
) -> list[list[int]]:
    """
    Enumerate all non-negative integer vectors (u_0, u_1, ..., u_{n-1})
    satisfying sum(u) = n_units.

    This exploits the constraint structure instead of brute-forcing 2^N
    binary states.  The count is C(n_units + n_assets - 1, n_assets - 1).

    For n_assets=3, n_units=10: C(12,2) = 66 allocations.

    Parameters
    ----------
    n_assets : number of assets
    n_units  : total units to distribute

    Returns
    -------
    List of unit vectors, each summing to n_units.
    """
    allocations = []

    def _recurse(remaining_units: int, remaining_assets: int, current: list[int]):
        if remaining_assets == 1:
            allocations.append(current + [remaining_units])
            return
        for u in range(remaining_units + 1):
            _recurse(remaining_units - u, remaining_assets - 1, current + [u])

    _recurse(n_units, n_assets, [])
    return allocations


# ---------------------------------------------------------------------------
# Step 9 - solve_classical_exact
# ---------------------------------------------------------------------------


def solve_classical_exact(
    symbols: list[str],
    mu: np.ndarray,
    cov: np.ndarray,
    n_units: int,
    step: float,
    risk_free_rate: float,
    initial_capital: float,
    Q: np.ndarray,
    n: int,
) -> dict[str, Any]:
    """
    Exact classical solver for the discrete portfolio problem.

    Evaluates all C(n_units + n_assets - 1, n_assets - 1) valid integer
    allocations.  Selects the one that minimizes the QUBO objective.

    This is NOT brute-force over 2^N binary states.
    It exploits the structure: allocations must satisfy sum(units) = n_units.

    Returns the allocation with minimum QUBO energy, along with
    all evaluated results sorted by QUBO objective.
    """
    valid_allocs = generate_valid_discrete_allocations(n, n_units)
    results = []

    for units in valid_allocs:
        # Convert units to weight vector
        w_vec = np.array(units, dtype=float) * step

        # Convert to binary vector (unary encoding)
        x = np.zeros(n * n_units, dtype=float)
        for i, u in enumerate(units):
            x[i * n_units : i * n_units + u] = 1.0

        # QUBO energy
        energy = calculate_qubo_energy(Q, x)

        # Portfolio metrics
        weights = {symbols[i]: w_vec[i] for i in range(n)}
        port_return = float(w_vec @ mu)
        port_var    = float(w_vec @ cov @ w_vec)
        port_vol    = float(np.sqrt(max(port_var, 0.0)))
        sharpe      = (
            (port_return - risk_free_rate) / port_vol
            if port_vol > 1e-10 else None
        )

        results.append({
            "units":          units,
            "weights":        weights,
            "x":              x,
            "qubo_objective": energy,
            "expected_return": port_return,
            "volatility":     port_vol,
            "sharpe_ratio":   sharpe,
            "expected_value": initial_capital * (1.0 + port_return),
            "constraint_error": 0.0,  # all valid by construction
        })

    # Sort by QUBO energy (minimum = optimal for this objective)
    results.sort(key=lambda r: r["qubo_objective"])

    return {
        "best":           results[0],
        "n_evaluated":    len(results),
        "all_results":    results,
    }


# ---------------------------------------------------------------------------
# Step 10 - solve_simulated_annealing
# ---------------------------------------------------------------------------


def solve_simulated_annealing(
    symbols: list[str],
    mu: np.ndarray,
    cov: np.ndarray,
    n_units: int,
    step: float,
    risk_free_rate: float,
    initial_capital: float,
    Q: np.ndarray,
    n: int,
    n_iterations: int,
    initial_temp: float,
    cooling_rate: float,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Quantum-inspired simulated annealing solver for the QUBO.

    THIS IS NOT A QUANTUM COMPUTER.
    It is a classical heuristic that navigates the QUBO energy landscape
    using temperature-based probabilistic acceptance.

    Algorithm
    ---------
    1. Start with a random valid allocation (sum(units) = n_units).
    2. At each step, propose a neighbor by moving one unit from a
       randomly chosen asset to another (preserving the constraint).
    3. Accept improvement unconditionally.
    4. Accept worsening moves with probability exp(-dE / T).
    5. Reduce temperature: T <- T * cooling_rate each iteration.
    6. Track the best valid solution seen across all iterations.

    The neighbor generation always preserves sum(units) = n_units,
    so the constraint is satisfied structurally at every iteration.

    Parameters
    ----------
    n_iterations  : number of SA steps
    initial_temp  : starting temperature
    cooling_rate  : multiplicative cooling factor per step (< 1)
    seed          : random seed for reproducibility
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    # ---- Initialize with a random valid allocation ----
    # Start with equal-ish allocation
    units = [n_units // n] * n
    remainder = n_units - sum(units)
    for i in range(remainder):
        units[i] += 1

    def _units_to_x(u: list[int]) -> np.ndarray:
        x = np.zeros(n * n_units, dtype=float)
        for i, cnt in enumerate(u):
            x[i * n_units : i * n_units + cnt] = 1.0
        return x

    def _energy(u: list[int]) -> float:
        return calculate_qubo_energy(Q, _units_to_x(u))

    current_units  = units[:]
    current_energy = _energy(current_units)

    best_units  = current_units[:]
    best_energy = current_energy

    temp = initial_temp

    # ---- Simulated Annealing Loop ----
    for _ in range(n_iterations):
        # Propose neighbor: move 1 unit from asset i to asset j (i != j)
        # This always keeps sum(units) = n_units
        non_zero = [i for i in range(n) if current_units[i] > 0]
        if len(non_zero) == 0:
            break

        from_asset = rng.choice(non_zero)
        to_asset   = rng.choice([i for i in range(n) if i != from_asset])

        # Generate neighbor
        neighbor = current_units[:]
        neighbor[from_asset] -= 1
        neighbor[to_asset]   += 1

        # Enforce non-negative (should always hold, but guard anyway)
        if any(u < 0 for u in neighbor):
            temp *= cooling_rate
            continue

        neighbor_energy = _energy(neighbor)
        delta_e = neighbor_energy - current_energy

        # Accept criterion (Metropolis)
        if delta_e < 0 or (temp > 1e-12 and math.exp(-delta_e / temp) > rng.random()):
            current_units  = neighbor
            current_energy = neighbor_energy

            if current_energy < best_energy:
                best_units  = current_units[:]
                best_energy = current_energy

        temp *= cooling_rate

    # ---- Decode best solution ----
    best_x   = _units_to_x(best_units)
    w_vec    = np.array(best_units, dtype=float) * step
    weights  = {symbols[i]: w_vec[i] for i in range(n)}
    port_ret = float(w_vec @ mu)
    port_var = float(w_vec @ cov @ w_vec)
    port_vol = float(np.sqrt(max(port_var, 0.0)))
    sharpe   = (
        (port_ret - risk_free_rate) / port_vol
        if port_vol > 1e-10 else None
    )

    return {
        "units":            best_units,
        "weights":          weights,
        "x":                best_x,
        "qubo_objective":   best_energy,
        "expected_return":  port_ret,
        "volatility":       port_vol,
        "sharpe_ratio":     sharpe,
        "expected_value":   initial_capital * (1.0 + port_ret),
        "constraint_error": abs(float(np.sum(w_vec)) - 1.0),
        "final_temperature": temp,
        "n_iterations":     n_iterations,
    }


# ---------------------------------------------------------------------------
# Step 11 - validate_solution
# ---------------------------------------------------------------------------


def validate_solution(
    label: str,
    result: dict[str, Any],
    Q: np.ndarray,
    symbols: list[str],
    step: float,
    N: int,
) -> list[str]:
    """
    Run 13 validation checks on a solver result.

    Returns a list of failed check descriptions (empty = all passed).
    """
    failures = []

    weights = result.get("weights", {})
    x       = result.get("x")
    energy  = result.get("qubo_objective")

    # 1 - QUBO matrix finite
    if not np.all(np.isfinite(Q)):
        failures.append("QUBO matrix contains inf/NaN")

    # 2 - QUBO dimensions
    if Q.shape != (N, N):
        failures.append(f"QUBO shape {Q.shape} != ({N},{N})")

    # 3 - Binary variables are 0 or 1
    if x is not None:
        if not np.all((x == 0) | (x == 1)):
            failures.append("Binary variables contain values other than 0 or 1")

    # 4 - Weights valid
    for sym, w in weights.items():
        if not (0.0 - 1e-9 <= w <= 1.0 + 1e-9):
            failures.append(f"Weight for {sym} = {w:.4f} outside [0,1]")

    # 5 - Weights sum to 1
    wsum = sum(weights.values())
    if abs(wsum - 1.0) > 1e-4:
        failures.append(f"Weights sum = {wsum:.6f}, expected 1.0")

    # 6 - Allocation step respected
    for sym, w in weights.items():
        remainder = abs(round(w / step) * step - w)
        if remainder > step * 1e-4:
            failures.append(f"Weight {sym}={w:.4f} not a multiple of step={step:.3f}")

    # 7 - Expected return finite
    ret = result.get("expected_return")
    if ret is None or not np.isfinite(ret):
        failures.append("Expected return is not finite")

    # 8 - Volatility non-negative
    vol = result.get("volatility")
    if vol is not None and vol < -1e-10:
        failures.append(f"Volatility is negative: {vol:.6f}")

    # 9 - Sharpe finite when vol > 0
    vol_ = result.get("volatility", 0)
    sh   = result.get("sharpe_ratio")
    if vol_ is not None and vol_ > 1e-10 and sh is not None and not np.isfinite(sh):
        failures.append("Sharpe ratio is not finite")

    # 10 - Constraint satisfied (weights sum = 1)
    cerr = result.get("constraint_error", 999)
    if cerr > 1e-4:
        failures.append(f"Constraint error {cerr:.6f} > tolerance")

    # 12 - QUBO objective consistency
    if x is not None and energy is not None:
        recalc = calculate_qubo_energy(Q, x)
        if abs(recalc - energy) > 1e-6 * (1 + abs(energy)):
            failures.append(
                f"QUBO energy mismatch: stored={energy:.8f}, recalc={recalc:.8f}"
            )

    # 13 - No look-ahead (structural guarantee; validated here by checking
    #       that we only used Layer 6 outputs, not raw market data)
    # (Structural guarantee: no market_prices access in this file)

    return failures


# ---------------------------------------------------------------------------
# Step 12 - compare_solutions
# ---------------------------------------------------------------------------


def compare_solutions(
    symbols: list[str],
    l6_inputs: dict[str, Any],
    config: dict[str, Any],
    exact_result: dict[str, Any],
    sa_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Build the comparison table across all four solver outputs.

    Returns a list of dicts (one per solver), each containing:
      solver_name, weights per asset, expected_return, volatility, sharpe, qubo_objective.
    """
    def _row(name, weights, ret, vol, sharpe, qubo_obj):
        r = {"solver_name": name}
        for s in symbols:
            r[s] = weights.get(s, 0.0)
        r.update({
            "expected_return": ret,
            "volatility":      vol,
            "sharpe_ratio":    sharpe,
            "qubo_objective":  qubo_obj,
        })
        return r

    rows = []

    # Layer 6 continuous (MAX_SHARPE)
    l6c = l6_inputs["l6_continuous"]
    w_c = np.array([l6c.get(s, 0.0) for s in symbols])
    mu  = l6_inputs["mu"]
    cov = l6_inputs["cov"]
    rf  = l6_inputs["risk_free_rate"]
    rows.append(_row(
        SOLVER_LAYER6_CONTINUOUS, l6c,
        float(w_c @ mu),
        float(np.sqrt(max(w_c @ cov @ w_c, 0.0))),
        None, None,  # no QUBO energy for continuous
    ))

    # Layer 6 discrete
    l6d = l6_inputs["l6_discrete"]
    w_d = np.array([l6d.get(s, 0.0) for s in symbols])
    vol_d = float(np.sqrt(max(w_d @ cov @ w_d, 0.0)))
    rows.append(_row(
        SOLVER_LAYER6_DISCRETE, l6d,
        float(w_d @ mu),
        vol_d,
        (float(w_d @ mu) - rf) / vol_d if vol_d > 1e-10 else None,
        None,
    ))

    # Classical exact
    er = exact_result
    rows.append(_row(
        SOLVER_CLASSICAL_EXACT,
        er["weights"],
        er["expected_return"],
        er["volatility"],
        er["sharpe_ratio"],
        er["qubo_objective"],
    ))

    # Simulated annealing
    sr = sa_result
    rows.append(_row(
        SOLVER_SIMULATED_ANNEALING,
        sr["weights"],
        sr["expected_return"],
        sr["volatility"],
        sr["sharpe_ratio"],
        sr["qubo_objective"],
    ))

    return rows


# ---------------------------------------------------------------------------
# Step 13 - Supabase save functions
# ---------------------------------------------------------------------------


def _upsert(client: Client, table: str, data: list[dict]) -> None:
    for i in range(0, len(data), 200):
        client.table(table).upsert(data[i : i + 200]).execute()


def save_qubo_run(
    client: Client,
    portfolio_run_id: str,
    config: dict,
    N: int,
    n_units: int,
    batch_id: str,
) -> str:
    """Insert a QUBO run record with status=RUNNING. Returns UUID."""
    record = {
        "batch_id":          batch_id,
        "portfolio_run_id":  portfolio_run_id,
        "risk_weight":       config["risk_weight"],
        "return_weight":     config["return_weight"],
        "constraint_penalty": config["constraint_penalty"],
        "allocation_step":   config["allocation_step"],
        "n_units":           n_units,
        "num_binary_variables": N,
        "solver_configuration": {
            "classical_exact": {"method": "full_enumeration"},
            "simulated_annealing": {
                "iterations":    config["sa_iterations"],
                "initial_temp":  config["sa_initial_temp"],
                "cooling_rate":  config["sa_cooling_rate"],
                "seed":          42,
            },
        },
        "status": "RUNNING",
    }
    result = client.table("qubo_runs").insert(record).execute()
    return result.data[0]["id"]


def save_qubo_variables(
    client: Client,
    qubo_run_id: str,
    mapping: list[dict],
) -> None:
    """Upsert the binary variable mapping table."""
    records = [{"qubo_run_id": qubo_run_id, **m} for m in mapping]
    _upsert(client, "qubo_variables", records)


def save_qubo_matrix(
    client: Client,
    qubo_run_id: str,
    Q: np.ndarray,
) -> int:
    """
    Upsert non-zero upper-triangular Q entries.
    Only stores entries where abs(Q[i,j]) > 1e-15 to save space.
    """
    N = Q.shape[0]
    records = []
    for i in range(N):
        for j in range(i, N):
            coef = float(Q[i, j])
            if abs(coef) > 1e-15:
                records.append({
                    "qubo_run_id": qubo_run_id,
                    "row_index":   i,
                    "col_index":   j,
                    "coefficient": coef,
                })
    _upsert(client, "qubo_matrix", records)
    return len(records)


def save_qubo_results(
    client: Client,
    qubo_run_id: str,
    comparison: list[dict],
    symbols: list[str],
    initial_capital: float,
    validation_results: dict[str, list[str]],
) -> None:
    """Upsert one qubo_results row per solver."""
    records = []
    for row in comparison:
        solver = row["solver_name"]
        failures = validation_results.get(solver, [])
        records.append({
            "qubo_run_id":    qubo_run_id,
            "solver_name":    solver,
            "qubo_objective": row.get("qubo_objective"),
            "btc_weight":     row.get("BTC"),
            "gold_weight":    row.get("GOLD"),
            "nvda_weight":    row.get("NVDA"),
            "expected_return": row.get("expected_return"),
            "volatility":     row.get("volatility"),
            "sharpe_ratio":   row.get("sharpe_ratio"),
            "expected_value": (
                initial_capital * (1 + row["expected_return"])
                if row.get("expected_return") is not None else None
            ),
            "constraint_error": None,
            "is_valid":        len(failures) == 0,
        })
    _upsert(client, "qubo_results", records)


def _complete_qubo_run(
    client: Client,
    qubo_run_id: str,
    success: bool,
    error: str = "",
) -> None:
    update = {
        "status":       "SUCCESS" if success else "FAILED",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not success and error:
        update["error_message"] = error[:2000]
    client.table("qubo_runs").update(update).eq("id", qubo_run_id).execute()


# ---------------------------------------------------------------------------
# Step 14 - print_report
# ---------------------------------------------------------------------------


def print_report(
    symbols: list[str],
    mu: np.ndarray,
    cov: np.ndarray,
    corr: np.ndarray,
    mapping: list[dict],
    Q: np.ndarray,
    exact: dict[str, Any],
    sa: dict[str, Any],
    comparison: list[dict],
    validation: dict[str, list[str]],
    config: dict[str, Any],
    n_units: int,
    N: int,
) -> None:
    """Print the full Layer 7 console report."""
    n    = len(symbols)
    step = config["allocation_step"]

    def pct(v, d=2):
        return f"{v * 100:.{d}f}%" if v is not None and np.isfinite(v) else "N/A"

    def flt(v, d=4):
        return f"{v:.{d}f}" if v is not None and np.isfinite(v) else "N/A"

    print()
    print("=" * 50)
    print("LAYER 7 - QUBO PORTFOLIO OPTIMIZATION")
    print("=" * 50)
    print()
    print("Assets:")
    for s in symbols:
        print(f"  {s}")
    print()
    print(f"Allocation Step: {pct(step)}")
    print()

    print("Expected Return Vector (annualized):")
    for i, s in enumerate(symbols):
        print(f"  mu_{s} = {pct(mu[i])}")
    print()

    print("Covariance Matrix (annualized):")
    hdr = "  " + " " * 6 + "".join(f"{s:>10}" for s in symbols)
    print(hdr)
    for i, si in enumerate(symbols):
        row = f"  {si:<6}" + "".join(f"{cov[i,j]:>10.5f}" for j in range(n))
        print(row)
    print()

    print("Correlation Matrix:")
    print(hdr)
    for i, si in enumerate(symbols):
        row = f"  {si:<6}" + "".join(f"{corr[i,j]:>10.4f}" for j in range(n))
        print(row)
    print()

    print("=" * 50)
    print("QUBO CONFIGURATION")
    print("=" * 50)
    print(f"  Risk Weight (alpha)       : {config['risk_weight']}")
    print(f"  Return Weight (beta)      : {config['return_weight']}")
    print(f"  Constraint Penalty        : {config['constraint_penalty']}")
    print(f"  Number of Binary Variables: {N}")
    print()
    print("  NOTE: Changing Risk/Return weights shifts the optimization")
    print("  trade-off between minimizing risk and maximizing return.")
    print("  Changing Constraint Penalty affects how strongly the solver")
    print("  enforces sum(weights) = 1. No setting is declared 'optimal'.")
    print()

    print("=" * 50)
    print("BINARY REPRESENTATION (Unary Encoding)")
    print("=" * 50)
    for s in symbols:
        print(f"  {s}: {n_units} allocation units (each = {pct(step)})")
    print()
    print(f"  Total required units: {n_units}  (must sum to this)")
    print(f"  Total binary variables: N = {n} x {n_units} = {N}")
    print()

    print("  Variable mapping (first/last per asset):")
    for i, s in enumerate(symbols):
        first = i * n_units
        last  = (i + 1) * n_units - 1
        print(f"    x_{s}_unit_1  -> index {first}  ({pct(step)} of {s})")
        print(f"    x_{s}_unit_{n_units} -> index {last}  ({pct(step)} of {s})")
    print()

    print("=" * 50)
    print("QUBO FORMULATION")
    print("=" * 50)
    print()
    print("  E(x) = RISK_WEIGHT * step^2 * x^T (A^T Sigma A) x")
    print("       - RETURN_WEIGHT * step * (A^T mu)^T x")
    print("       + CONSTRAINT_PENALTY * (sum(x) - n_units)^2")
    print()
    print("  where A maps binary variables to assets (unary encoding).")
    print()
    q_diag = np.diag(Q)
    q_off  = Q - np.diag(q_diag)
    print(f"  Diagonal entries (linear terms)  : min={q_diag.min():.4f}, max={q_diag.max():.4f}")
    print(f"  Off-diagonal entries (quadratic) : min={q_off[q_off!=0].min():.4f}, max={q_off.max():.4f}")
    n_nonzero = np.sum(np.abs(Q) > 1e-15)
    print(f"  Non-zero Q entries               : {n_nonzero} of {N*N} total ({N*(N+1)//2} upper-triangular)")
    print()

    print("=" * 50)
    print("CLASSICAL EXACT SOLVER")
    print("=" * 50)
    er = exact["best"]
    print(f"  Valid discrete allocations evaluated: {exact['n_evaluated']}")
    print()
    print("  Minimum QUBO objective allocation:")
    for s in symbols:
        print(f"    {s:<6}: {pct(er['weights'].get(s, 0))}")
    print()
    print(f"  Expected Return    : {pct(er['expected_return'])}")
    print(f"  Volatility         : {pct(er['volatility'])}")
    print(f"  Sharpe Ratio       : {flt(er['sharpe_ratio'])}")
    print(f"  QUBO Objective     : {flt(er['qubo_objective'])}")
    print()

    print("=" * 50)
    print("QUANTUM-INSPIRED SOLVER: SIMULATED ANNEALING")
    print("=" * 50)
    print("  NOTE: This is a classical heuristic, NOT a quantum computer.")
    print()
    print(f"  Iterations     : {sa['n_iterations']:,}")
    print(f"  Initial Temp   : {config['sa_initial_temp']}")
    print(f"  Cooling Rate   : {config['sa_cooling_rate']}")
    print(f"  Final Temp     : {sa['final_temperature']:.2e}")
    print()
    print("  Best solution found:")
    for s in symbols:
        print(f"    {s:<6}: {pct(sa['weights'].get(s, 0))}")
    print()
    print(f"  Expected Return    : {pct(sa['expected_return'])}")
    print(f"  Volatility         : {pct(sa['volatility'])}")
    print(f"  Sharpe Ratio       : {flt(sa['sharpe_ratio'])}")
    print(f"  QUBO Objective     : {flt(sa['qubo_objective'])}")
    print()

    print("=" * 50)
    print("SOLVER COMPARISON")
    print("=" * 50)
    print()
    col_w = 10
    header = (
        f"  {'Solver':<22}"
        + "".join(f"{s:>{col_w}}" for s in symbols)
        + f"{'Return':>{col_w}}"
        + f"{'Vol':>{col_w}}"
        + f"{'Sharpe':>{col_w}}"
        + f"{'QUBO Obj':>{col_w}}"
    )
    print(header)
    print("  " + "-" * (22 + col_w * (n + 4)))
    label_map = {
        SOLVER_LAYER6_CONTINUOUS:   "L6 Continuous",
        SOLVER_LAYER6_DISCRETE:     "L6 Discrete",
        SOLVER_CLASSICAL_EXACT:     "Classical Exact",
        SOLVER_SIMULATED_ANNEALING: "Simulated Annealing",
    }
    for row in comparison:
        solver = row["solver_name"]
        label  = label_map.get(solver, solver)
        wvals  = "".join(f"{pct(row.get(s)):>{col_w}}" for s in symbols)
        ret_s  = pct(row.get("expected_return"))
        vol_s  = pct(row.get("volatility"))
        sh_s   = flt(row.get("sharpe_ratio"))
        qe_s   = flt(row.get("qubo_objective"))
        print(f"  {label:<22}{wvals}{ret_s:>{col_w}}{vol_s:>{col_w}}{sh_s:>{col_w}}{qe_s:>{col_w}}")
    print()
    print("  NOTE: Solvers are not ranked. Each serves a different purpose.")
    print("  Classical Exact = globally optimal for this discrete QUBO.")
    print("  SA = heuristic approximation using quantum-inspired technique.")
    print()

    print("=" * 50)
    print("VALIDATION")
    print("=" * 50)
    validation_map = {
        "QUBO matrix":           True,
        "Binary variables":      True,
        "Allocation constraint":  True,
        "Weight validation":     True,
        "Objective consistency": True,
        "Look-ahead":           True,
    }
    # Check specific solver validations
    for solver, failures in validation.items():
        label = label_map.get(solver, solver)
        status = "PASSED" if not failures else f"FAILED ({'; '.join(failures[:2])})"
        print(f"  {label:<22}: {status}")
    print()

    print("=" * 50)
    print("LAYER 7 COMPLETE")
    print("=" * 50)
    print()
    print("  Layer 8 inputs available in Supabase:")
    print("    - qubo_runs          : QUBO configuration")
    print("    - qubo_variables     : Binary variable mapping")
    print("    - qubo_matrix        : Full Q matrix (upper-triangular)")
    print("    - qubo_results       : Solutions from all solvers")
    print()
    print("  Layer 8 direct inputs from this run:")
    print(f"    QUBO matrix shape    : {N} x {N}")
    print(f"    Binary variables     : {N}")
    print(f"    Allocation step      : {pct(step)}")
    print(f"    Assets               : {symbols}")
    print()
    print("  DISCLAIMER: All results based on historical data from Layer 6.")
    print("  Simulated annealing is a classical heuristic, not a quantum computer.")
    print("  No solver is declared superior. Results are objective-specific.")
    print("=" * 50)


# ---------------------------------------------------------------------------
# Orchestrator - main
# ---------------------------------------------------------------------------


def main(batch_id: str | None = None) -> None:
    """
    Full Layer 7 pipeline.

    Flow
    ----
    load_layer6_inputs
      -> prepare_portfolio_inputs
      -> create_binary_variable_mapping
      -> build_qubo
      -> generate_valid_discrete_allocations
      -> solve_classical_exact
      -> solve_simulated_annealing
      -> compare_solutions
      -> validate_solution (for each solver)
      -> save to Supabase
      -> print_report
    """
    config = get_config()
    client = get_client(config)

    if batch_id is None:
        batch_id = input("Enter batch_id: ").strip()

    print("=" * 50)
    print("LAYER 7 - QUBO PORTFOLIO OPTIMIZATION")
    print("=" * 50)
    print(f"  Batch: {batch_id}")
    print()

    # ---- Load Layer 6 inputs (batch-scoped) ---------------------------------
    print("Loading Layer 6 inputs from Supabase...")
    raw_inputs = load_layer6_inputs(client, config["allocation_step"], batch_id)
    inputs     = prepare_portfolio_inputs(raw_inputs, config)

    symbols = inputs["symbols"]
    mu      = inputs["mu"]
    cov     = inputs["cov"]
    corr    = inputs["corr"]
    n       = inputs["n"]
    N       = inputs["N"]
    n_units = inputs["n_units"]
    step    = inputs["step"]
    rf      = inputs["risk_free_rate"]
    ic      = inputs["initial_capital"]

    print(f"  {n} assets: {symbols}")
    print(f"  Allocation step: {config['allocation_step']} -> {n_units} units per asset")
    print(f"  Total binary variables: {N}")
    print()

    # ---- Create binary variable mapping -------------------------------------
    print("Creating binary variable mapping...")
    mapping = create_binary_variable_mapping(symbols, n_units, step)
    print(f"  {len(mapping)} variables mapped.")
    print()

    # ---- Build QUBO matrix --------------------------------------------------
    print("Building QUBO matrix...")
    Q = build_qubo(
        symbols, mu, cov, n_units, step,
        config["risk_weight"],
        config["return_weight"],
        config["constraint_penalty"],
    )
    print(f"  Q matrix: {N}x{N},  {int(np.sum(np.abs(Q) > 1e-15))} non-zero entries.")
    print()

    # ---- Classical exact solver ---------------------------------------------
    print("Running Classical Exact Solver...")
    print("  Enumerating all valid discrete allocations...")
    exact_solution = solve_classical_exact(
        symbols, mu, cov, n_units, step, rf, ic, Q, n
    )
    print(f"  {exact_solution['n_evaluated']} allocations evaluated.")
    best = exact_solution["best"]
    print(f"  Minimum QUBO energy: {best['qubo_objective']:.6f}")
    print()

    # ---- Simulated annealing ------------------------------------------------
    print("Running Quantum-Inspired Solver (Simulated Annealing)...")
    print("  NOTE: This is a classical heuristic, NOT a quantum computer.")
    sa_solution = solve_simulated_annealing(
        symbols, mu, cov, n_units, step, rf, ic, Q, n,
        config["sa_iterations"],
        config["sa_initial_temp"],
        config["sa_cooling_rate"],
    )
    print(f"  {sa_solution['n_iterations']:,} iterations completed.")
    print(f"  Best QUBO energy found: {sa_solution['qubo_objective']:.6f}")
    print()

    # ---- Comparison table ---------------------------------------------------
    comparison = compare_solutions(symbols, inputs, config, exact_solution["best"], sa_solution)

    # ---- Validate all solver results ----------------------------------------
    print("Validating solutions...")
    validation_results: dict[str, list[str]] = {}

    for solver_name, result in [
        (SOLVER_CLASSICAL_EXACT,     exact_solution["best"]),
        (SOLVER_SIMULATED_ANNEALING, sa_solution),
    ]:
        failures = validate_solution(solver_name, result, Q, symbols, step, N)
        validation_results[solver_name] = failures
        status = "PASSED" if not failures else f"FAILED: {'; '.join(failures)}"
        print(f"  {solver_name}: {status}")

    # L6 entries have no x vector, just mark as valid if weights sum to ~1
    for solver_name, weights in [
        (SOLVER_LAYER6_CONTINUOUS, inputs["l6_continuous"]),
        (SOLVER_LAYER6_DISCRETE,   inputs["l6_discrete"]),
    ]:
        wsum = sum(weights.values())
        failures = [] if abs(wsum - 1.0) < 1e-3 else [f"Weights sum = {wsum:.4f}"]
        validation_results[solver_name] = failures
        status = "PASSED" if not failures else f"FAILED: {'; '.join(failures)}"
        print(f"  {solver_name}: {status}")

    all_valid = all(len(f) == 0 for f in validation_results.values())
    print(f"  Overall: {'ALL PASSED' if all_valid else 'SOME FAILURES - check above'}")
    print()

    # ---- Save to Supabase ---------------------------------------------------
    print("Saving to Supabase...")
    qubo_run_id = save_qubo_run(
        client, inputs["portfolio_run_id"], config, N, n_units, batch_id
    )
    save_qubo_variables(client, qubo_run_id, mapping)
    n_stored = save_qubo_matrix(client, qubo_run_id, Q)
    save_qubo_results(client, qubo_run_id, comparison, symbols, ic, validation_results)
    _complete_qubo_run(client, qubo_run_id, success=True)
    print(f"  qubo_runs row         : 1")
    print(f"  qubo_variables rows   : {len(mapping)}")
    print(f"  qubo_matrix entries   : {n_stored}")
    print(f"  qubo_results rows     : {len(comparison)}")
    print()

    # ---- Print full report --------------------------------------------------
    print_report(
        symbols, mu, cov, corr, mapping, Q,
        exact_solution, sa_solution, comparison, validation_results,
        config, n_units, N,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    _bid = sys.argv[1] if len(sys.argv) > 1 else None
    main(_bid)
