-- =============================================================
-- Layer 7: QUBO Portfolio Optimization - Schema
-- Run once in Supabase SQL Editor before running qubo_optimizer.py
-- =============================================================

-- -----------------------------------------------------------
-- qubo_runs
--
-- One record per QUBO optimizer invocation.
-- References the Layer 6 portfolio_optimization_runs parent.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS qubo_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- FK to the Layer 6 run that supplied mu / Sigma / step
    portfolio_run_id UUID
        REFERENCES portfolio_optimization_runs(id)
        ON DELETE SET NULL,

    -- QUBO objective weights (configurable)
    risk_weight        NUMERIC NOT NULL,
    return_weight      NUMERIC NOT NULL,
    constraint_penalty NUMERIC NOT NULL,

    -- Allocation step carried from Layer 6
    allocation_step NUMERIC NOT NULL,

    -- Number of allocation units per asset  (= 1 / allocation_step)
    n_units INTEGER NOT NULL,

    -- Total binary variables  (n_assets * n_units)
    num_binary_variables INTEGER NOT NULL,

    -- Solvers attempted and configuration as JSONB
    solver_configuration JSONB,

    -- RUNNING | SUCCESS | FAILED
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),

    error_message TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_qubo_runs_portfolio_run
    ON qubo_runs(portfolio_run_id);

-- -----------------------------------------------------------
-- qubo_variables
--
-- Documents the mapping from binary variable index to
-- asset / allocation-unit meaning.
--
-- Example (step=0.10, 10 units per asset):
--   index=0  BTC unit_1  0.10
--   index=1  BTC unit_2  0.10
--   ...
--   index=9  BTC unit_10 0.10
--   index=10 GOLD unit_1  0.10
--   ...
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS qubo_variables (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    qubo_run_id UUID NOT NULL
        REFERENCES qubo_runs(id)
        ON DELETE CASCADE,

    variable_index  INTEGER NOT NULL,
    variable_name   TEXT NOT NULL,       -- e.g. "x_BTC_unit_1"
    asset_symbol    TEXT NOT NULL,       -- e.g. "BTC"
    allocation_unit INTEGER NOT NULL,    -- unit number 1..n_units
    allocation_value NUMERIC NOT NULL,   -- = allocation_step

    UNIQUE(qubo_run_id, variable_index)
);

CREATE INDEX IF NOT EXISTS idx_qubo_vars_run
    ON qubo_variables(qubo_run_id);

-- -----------------------------------------------------------
-- qubo_results
--
-- One row per (qubo_run, solver).
-- Stores decoded weights and portfolio metrics for each solver.
--
-- solver_name values:
--   LAYER6_CONTINUOUS
--   LAYER6_DISCRETE
--   CLASSICAL_EXACT
--   SIMULATED_ANNEALING
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS qubo_results (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    qubo_run_id UUID NOT NULL
        REFERENCES qubo_runs(id)
        ON DELETE CASCADE,

    -- Identifies which solver produced this result
    solver_name TEXT NOT NULL,

    -- QUBO objective value: risk - return + penalty
    qubo_objective NUMERIC,

    -- Decoded portfolio weights
    btc_weight  NUMERIC,
    gold_weight NUMERIC,
    nvda_weight NUMERIC,

    -- Portfolio metrics (same formulas as Layer 6)
    expected_return NUMERIC,
    volatility      NUMERIC,
    sharpe_ratio    NUMERIC,

    -- initial_capital * (1 + expected_return)  [historical estimate only]
    expected_value NUMERIC,

    -- |sum(weights) - 1|, should be near zero for valid solutions
    constraint_error NUMERIC,

    -- Did all validation checks pass?
    is_valid BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(qubo_run_id, solver_name)
);

CREATE INDEX IF NOT EXISTS idx_qubo_results_run
    ON qubo_results(qubo_run_id);

-- -----------------------------------------------------------
-- qubo_matrix
--
-- Stores the upper-triangular Q matrix coefficients.
-- Only non-zero entries are stored for efficiency.
--
-- The QUBO energy is:  sum_{i<=j} Q[i,j] * x[i] * x[j]
-- (diagonal entries are linear terms, off-diagonal are quadratic)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS qubo_matrix (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    qubo_run_id UUID NOT NULL
        REFERENCES qubo_runs(id)
        ON DELETE CASCADE,

    row_index   INTEGER NOT NULL,    -- variable index i
    col_index   INTEGER NOT NULL,    -- variable index j (>= i)
    coefficient NUMERIC NOT NULL,    -- Q[i,j]

    UNIQUE(qubo_run_id, row_index, col_index)
);

CREATE INDEX IF NOT EXISTS idx_qubo_matrix_run
    ON qubo_matrix(qubo_run_id);
