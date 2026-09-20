-- =============================================================
-- Layer 6: Portfolio Optimization – Schema
-- Run once in Supabase SQL Editor before running portfolio_optimizer.py
-- =============================================================

-- -----------------------------------------------------------
-- portfolio_optimization_runs
--
-- One row per optimizer invocation.
-- Stores all configuration so results are fully reproducible.
-- status: RUNNING → SUCCESS | FAILED
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolio_optimization_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- MINIMUM_VOLATILITY | MAXIMUM_SHARPE | MAXIMUM_RETURN | TARGET_RETURN
    objective TEXT NOT NULL,

    initial_capital NUMERIC NOT NULL,

    risk_free_rate NUMERIC NOT NULL,

    -- NULL means use all available data
    lookback_days INTEGER,

    -- ISO date strings for the actual data window used
    data_start_date DATE,
    data_end_date   DATE,

    -- Step size for discrete allocation (e.g. 0.10 = 10%)
    allocation_step NUMERIC NOT NULL,

    -- Minimum required return for TARGET_RETURN objective (may be NULL)
    target_return NUMERIC,

    -- Additional optimizer constraints as JSONB (for reproducibility)
    constraints JSONB,

    -- RUNNING | SUCCESS | FAILED
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),

    error_message TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_opt_runs_objective
    ON portfolio_optimization_runs(objective);

CREATE INDEX IF NOT EXISTS idx_opt_runs_status
    ON portfolio_optimization_runs(status);

-- -----------------------------------------------------------
-- portfolio_allocations
--
-- Per-asset allocation for each optimization run.
-- Stores both continuous (scipy output) and discrete (rounded)
-- weights so Layer 7 can consume either.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolio_allocations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id UUID NOT NULL
        REFERENCES portfolio_optimization_runs(id)
        ON DELETE CASCADE,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    -- Human-readable ticker for fast reporting queries
    asset_symbol TEXT NOT NULL,

    -- Raw scipy optimizer output (0..1)
    continuous_weight NUMERIC NOT NULL,

    -- Rounded to the nearest allocation_step (e.g. 0.1), sum=1 guaranteed
    discrete_weight NUMERIC NOT NULL,

    -- Individual asset metrics used in this optimization window
    expected_return          NUMERIC,
    expected_volatility      NUMERIC,
    -- Marginal volatility contribution: w_i * (Sigma @ w)_i / portfolio_vol
    volatility_contribution  NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(run_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_opt_allocations_run
    ON portfolio_allocations(run_id);

-- -----------------------------------------------------------
-- portfolio_results
--
-- Aggregate metrics for each optimization run.
-- Also stores the benchmark portfolios (equal-weight, single-asset).
-- portfolio_type: OPTIMIZED | EQUAL_WEIGHT | SINGLE_ASSET
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolio_results (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id UUID NOT NULL
        REFERENCES portfolio_optimization_runs(id)
        ON DELETE CASCADE,

    -- OPTIMIZED | EQUAL_WEIGHT | SINGLE_ASSET
    portfolio_type TEXT NOT NULL
        CHECK (portfolio_type IN ('OPTIMIZED', 'EQUAL_WEIGHT', 'SINGLE_ASSET')),

    -- For SINGLE_ASSET rows, which asset this represents
    single_asset_symbol TEXT,

    portfolio_return    NUMERIC,
    portfolio_volatility NUMERIC,
    sharpe_ratio        NUMERIC,

    -- initial_capital * (1 + portfolio_return)
    -- Clearly labelled: historical expected value, NOT a backtest result
    expected_final_value NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opt_results_run
    ON portfolio_results(run_id);

-- -----------------------------------------------------------
-- portfolio_covariance_inputs
--
-- Stores the annualized covariance and correlation matrix used
-- in each optimization run, for full reproducibility and
-- Layer 7 consumption.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolio_covariance_inputs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id UUID NOT NULL
        REFERENCES portfolio_optimization_runs(id)
        ON DELETE CASCADE,

    asset_1_symbol TEXT NOT NULL,
    asset_2_symbol TEXT NOT NULL,

    -- Annualized covariance (Sigma[i,j])
    covariance NUMERIC NOT NULL,

    -- Pearson correlation derived from covariance
    correlation NUMERIC NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(run_id, asset_1_symbol, asset_2_symbol)
);

CREATE INDEX IF NOT EXISTS idx_opt_cov_run
    ON portfolio_covariance_inputs(run_id);
