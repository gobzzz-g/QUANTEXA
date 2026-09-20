-- =============================================================
-- Layer 2: Quantitative Analysis Engine  –  Schema
-- Run once in Supabase SQL Editor before running quant_engine.py
-- =============================================================

-- -----------------------------------------------------------
-- asset_indicators
-- Per-asset per-date rolling technical indicators.
-- One row per (asset, trading date).
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_indicators (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    date DATE NOT NULL,

    -- Daily log-linear return: (close_t / close_{t-1}) - 1
    daily_return NUMERIC,

    -- Simple Moving Averages (NaN until window is full)
    sma_20  NUMERIC,
    sma_50  NUMERIC,
    sma_200 NUMERIC,

    -- Exponential Moving Averages (defined from first observation)
    ema_20  NUMERIC,
    ema_50  NUMERIC,
    ema_200 NUMERIC,

    -- Rolling standard deviation of daily_return (annualised by caller)
    volatility_20  NUMERIC,
    volatility_60  NUMERIC,
    volatility_252 NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_asset_indicator_date
        UNIQUE (asset_id, date)
);

CREATE INDEX IF NOT EXISTS idx_asset_indicators_asset_date
    ON asset_indicators(asset_id, date);

CREATE INDEX IF NOT EXISTS idx_asset_indicators_date
    ON asset_indicators(date);

-- -----------------------------------------------------------
-- asset_statistics
-- Per-asset summary statistics over a specific date range.
-- Re-running the engine with updated data produces a new row
-- only when the date range changes; otherwise the existing row
-- is updated in place (UPSERT on asset_id + start_date + end_date).
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_statistics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    -- Date range of the underlying price data used
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL,

    -- Return metrics
    -- Annualisation convention: 252 trading periods for all assets.
    total_return        NUMERIC,   -- (last_close / first_close) - 1
    annualized_return   NUMERIC,   -- geometric: (1+TR)^(252/n_days) - 1
    annualized_volatility NUMERIC, -- std(daily_returns) * sqrt(252)

    -- Risk-adjusted metric
    -- Sharpe = (ann_return - risk_free_rate) / ann_volatility
    -- risk_free_rate sourced from RISK_FREE_RATE env var (default 0.0)
    sharpe_ratio NUMERIC,

    -- Maximum drawdown
    max_drawdown             NUMERIC,  -- always <= 0
    max_drawdown_start_date  DATE,     -- peak before trough
    max_drawdown_trough_date DATE,     -- date of deepest loss
    max_drawdown_recovery_date DATE,   -- first date price >= peak (NULL if not recovered)

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_asset_stat_period
        UNIQUE (asset_id, start_date, end_date)
);

CREATE INDEX IF NOT EXISTS idx_asset_statistics_asset
    ON asset_statistics(asset_id);

-- -----------------------------------------------------------
-- asset_correlations
-- Pairwise rolling return correlations between assets.
--
-- Rules enforced by the database:
--   • asset_1_id < asset_2_id  (no GOLD-BTC AND BTC-GOLD for same date)
--   • asset_1_id != asset_2_id (no self-correlation)
--   • window_days IN (30, 60, 90)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_correlations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_1_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    asset_2_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    -- Trading date on which the rolling window ends
    date DATE NOT NULL,

    -- Rolling window in trading-day observations
    window_days INTEGER NOT NULL
        CHECK (window_days IN (30, 60, 90)),

    -- Pearson correlation of daily returns; always in [-1, 1]
    correlation NUMERIC,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Idempotency key
    CONSTRAINT unique_asset_correlation
        UNIQUE (asset_1_id, asset_2_id, date, window_days),

    -- Structural constraints
    CONSTRAINT no_self_correlation
        CHECK (asset_1_id != asset_2_id),

    -- Enforce canonical pair ordering (smaller UUID first)
    CONSTRAINT ordered_asset_pair
        CHECK (asset_1_id < asset_2_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_correlations_pair_date
    ON asset_correlations(asset_1_id, asset_2_id, date);

CREATE INDEX IF NOT EXISTS idx_asset_correlations_date
    ON asset_correlations(date);

CREATE INDEX IF NOT EXISTS idx_asset_correlations_window
    ON asset_correlations(window_days);