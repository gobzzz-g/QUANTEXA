-- =============================================================
-- Layer 5: Robustness & Market Regime Analysis Engine – Schema
-- Run once in Supabase SQL Editor before running robustness_engine.py
-- =============================================================

-- -----------------------------------------------------------
-- market_regimes
--
-- Deterministic rule-based regime for every (asset, date).
-- Trend:     SMA50 vs SMA200            → BULL / BEAR / UNKNOWN
-- Volatility: vol_20 vs expanding median → HIGH / LOW / UNKNOWN
-- Combined:  4 regimes + UNKNOWN
--
-- Look-ahead guarantee: volatility_threshold is computed using
-- an expanding (causal) median – never uses future observations.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_regimes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    date DATE NOT NULL,

    -- BULL | BEAR | UNKNOWN
    trend_state TEXT NOT NULL,

    -- HIGH_VOLATILITY | LOW_VOLATILITY | UNKNOWN
    volatility_state TEXT NOT NULL,

    -- BULL_LOW_VOL | BULL_HIGH_VOL | BEAR_LOW_VOL | BEAR_HIGH_VOL | UNKNOWN
    regime TEXT NOT NULL,

    -- SMA50 / SMA200 values used for trend classification
    trend_value NUMERIC,          -- SMA50 / SMA200 ratio stored for auditability

    -- vol_20 observed on this date
    volatility_value NUMERIC,

    -- expanding-median threshold used on this date
    volatility_threshold NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(asset_id, date)
);

CREATE INDEX IF NOT EXISTS idx_market_regimes_asset_date
    ON market_regimes(asset_id, date);

CREATE INDEX IF NOT EXISTS idx_market_regimes_regime
    ON market_regimes(regime);

-- -----------------------------------------------------------
-- robustness_results
--
-- One row per (asset, strategy, params, test_type, test_value, period).
-- test_type  : PARAMETER | TRANSACTION_COST | TIME_PERIOD
-- test_value : JSONB encoding what is varied in this row
--
-- PARAMETER test:
--   parameters  = strategy params   (e.g. {fast_window:10, slow_window:30})
--   test_value  = same as parameters (shows what is being swept)
--
-- TRANSACTION_COST test:
--   parameters  = default strategy params
--   test_value  = {transaction_cost: 0.001}
--
-- TIME_PERIOD test:
--   parameters  = default strategy params
--   test_value  = {period_name: "2023_2024"}
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS robustness_results (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    strategy_name TEXT NOT NULL,

    parameters JSONB NOT NULL,

    -- PARAMETER | TRANSACTION_COST | TIME_PERIOD
    test_type TEXT NOT NULL,

    -- JSONB encoding of what is being varied
    test_value JSONB NOT NULL,

    start_date DATE NOT NULL,

    end_date DATE NOT NULL,

    initial_capital NUMERIC NOT NULL,

    final_portfolio_value NUMERIC,

    total_return NUMERIC,

    annualized_return NUMERIC,

    annualized_volatility NUMERIC,

    sharpe_ratio NUMERIC,

    max_drawdown NUMERIC,

    trades INTEGER,

    win_rate NUMERIC,

    transaction_costs NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_robustness_result
        UNIQUE(
            asset_id,
            strategy_name,
            parameters,
            test_type,
            test_value,
            start_date,
            end_date
        )
);

CREATE INDEX IF NOT EXISTS idx_robustness_asset_strategy
    ON robustness_results(asset_id, strategy_name);

CREATE INDEX IF NOT EXISTS idx_robustness_test_type
    ON robustness_results(test_type);

-- -----------------------------------------------------------
-- strategy_regime_performance
--
-- Performance metrics for each (asset, strategy, params) broken
-- down by market regime.  Uses Layer 4 equity/trade data.
--
-- start_date / end_date = first and last date when this regime
-- was active in the backtest period (may be non-contiguous days
-- aggregated into one summary row).
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS strategy_regime_performance (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    strategy_name TEXT NOT NULL,

    parameters JSONB NOT NULL,

    -- BULL_LOW_VOL | BULL_HIGH_VOL | BEAR_LOW_VOL | BEAR_HIGH_VOL | UNKNOWN
    regime TEXT NOT NULL,

    start_date DATE NOT NULL,

    end_date DATE NOT NULL,

    trading_days INTEGER,

    trades INTEGER,

    total_return NUMERIC,

    annualized_return NUMERIC,

    annualized_volatility NUMERIC,

    sharpe_ratio NUMERIC,

    max_drawdown NUMERIC,

    winning_trades INTEGER,

    losing_trades INTEGER,

    win_rate NUMERIC,

    transaction_costs NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_regime_performance
        UNIQUE(
            asset_id,
            strategy_name,
            parameters,
            regime,
            start_date,
            end_date
        )
);

CREATE INDEX IF NOT EXISTS idx_regime_perf_asset_strategy
    ON strategy_regime_performance(asset_id, strategy_name);

CREATE INDEX IF NOT EXISTS idx_regime_perf_regime
    ON strategy_regime_performance(regime);
