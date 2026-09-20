-- =============================================================
-- Layer 4: Backtesting Engine  –  Schema
-- Run once in Supabase SQL Editor before running backtest_engine.py
-- =============================================================

-- -----------------------------------------------------------
-- backtest_runs
--
-- One row per backtest experiment.
-- Records the full configuration so results are reproducible.
-- status transitions: RUNNING -> SUCCESS | FAILED
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    strategy_name TEXT NOT NULL,

    -- Exact strategy parameters (e.g. {"fast_window": 20, "slow_window": 50})
    parameters JSONB NOT NULL,

    initial_capital NUMERIC NOT NULL,

    transaction_cost_rate NUMERIC NOT NULL,

    slippage_rate NUMERIC NOT NULL,

    start_date DATE NOT NULL,

    end_date DATE NOT NULL,

    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),

    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_asset
    ON backtest_runs(asset_id);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy
    ON backtest_runs(strategy_name);

-- -----------------------------------------------------------
-- backtest_equity
--
-- Daily equity curve for each backtest run.
-- One row per (backtest_run, trading_date).
--
-- Columns:
--   position  0=flat, 1=long  (no short selling in this layer)
--   daily_pnl NULL on first day (no prior day to diff)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_equity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    backtest_run_id UUID NOT NULL
        REFERENCES backtest_runs(id)
        ON DELETE CASCADE,

    date DATE NOT NULL,

    cash NUMERIC NOT NULL,

    units NUMERIC NOT NULL,

    close_price NUMERIC NOT NULL,

    market_value NUMERIC NOT NULL,

    portfolio_value NUMERIC NOT NULL,

    daily_pnl NUMERIC,

    daily_return NUMERIC,

    position INTEGER NOT NULL
        CHECK (position IN (0, 1)),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(backtest_run_id, date)
);

CREATE INDEX IF NOT EXISTS idx_backtest_equity_run_date
    ON backtest_equity(backtest_run_id, date);

-- -----------------------------------------------------------
-- backtest_trades
--
-- Individual trade records.
-- status: OPEN (position still held at backtest end) | CLOSED
--
-- gross_pnl = exit_value - entry_value
-- net_pnl   = gross_pnl - entry_transaction_cost - exit_transaction_cost
-- return_pct = net_pnl / entry_value
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_trades (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    backtest_run_id UUID NOT NULL
        REFERENCES backtest_runs(id)
        ON DELETE CASCADE,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    strategy_name TEXT NOT NULL,

    parameters JSONB NOT NULL,

    -- Signal date: the date the strategy generated the entry signal (T)
    signal_date DATE,

    entry_date DATE NOT NULL,       -- Execution date (T+1)

    entry_price NUMERIC NOT NULL,   -- Slippage-adjusted open price

    exit_date DATE,                 -- NULL if position still open

    exit_price NUMERIC,

    units NUMERIC NOT NULL,

    entry_value NUMERIC NOT NULL,

    exit_value NUMERIC,

    entry_transaction_cost NUMERIC NOT NULL DEFAULT 0,

    exit_transaction_cost NUMERIC DEFAULT 0,

    gross_pnl NUMERIC,

    net_pnl NUMERIC,

    return_pct NUMERIC,

    holding_period_days INTEGER,

    status TEXT NOT NULL
        CHECK (status IN ('OPEN', 'CLOSED')),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_run
    ON backtest_trades(backtest_run_id);

-- -----------------------------------------------------------
-- backtest_metrics
--
-- Flat key-value store for scalar performance metrics.
-- metric_value is NUMERIC; date-based metrics are stored
-- as text in the metric_name (e.g. "max_drawdown_trough_date")
-- with their ISO-8601 string serialised as epoch days in
-- metric_value for portability.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    backtest_run_id UUID NOT NULL
        REFERENCES backtest_runs(id)
        ON DELETE CASCADE,

    metric_name TEXT NOT NULL,

    metric_value NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(backtest_run_id, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_backtest_metrics_run
    ON backtest_metrics(backtest_run_id);

-- -----------------------------------------------------------
-- benchmark_results
--
-- Buy-and-Hold benchmark performance per asset.
-- benchmark_name = 'BUY_AND_HOLD' for this layer.
--
-- Unique on (asset_id, benchmark_name, start_date, end_date,
--            initial_capital) so upserts are idempotent.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS benchmark_results (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    benchmark_name TEXT NOT NULL,

    start_date DATE NOT NULL,

    end_date DATE NOT NULL,

    initial_capital NUMERIC NOT NULL,

    final_value NUMERIC,

    total_return NUMERIC,

    annualized_return NUMERIC,

    annualized_volatility NUMERIC,

    sharpe_ratio NUMERIC,

    max_drawdown NUMERIC,

    transaction_cost NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_benchmark
        UNIQUE (asset_id, benchmark_name, start_date, end_date, initial_capital)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_asset
    ON benchmark_results(asset_id);
