-- =============================================================
-- Layer 3: Strategy Engine  –  Schema
-- Run once in Supabase SQL Editor before running strategy_engine.py
-- =============================================================

-- -----------------------------------------------------------
-- strategy_signals
--
-- One row per (asset, date, strategy_name, parameters).
-- The JSONB parameters column stores the exact configuration
-- used so that different parameterisations of the same
-- strategy are treated as distinct experiments.
--
-- Signal convention (stored values):
--     1  = LONG              (bullish signal)
--     0  = FLAT / NO ACTION  (neutral)
--    -1  = EXIT / SHORT-STYLE (bearish signal)
--
-- IMPORTANT: -1 does NOT automatically mean a short position.
-- The backtesting layer (Layer 4) decides position direction.
--
-- Rows are only inserted when a signal can be generated.
-- Dates where required indicators are unavailable (NULLs in
-- asset_indicators) produce no row here.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS strategy_signals (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    -- Calendar date the signal applies to.
    -- signal_date is when the indicator was computed;
    -- execution_date is determined by the backtesting layer.
    date DATE NOT NULL,

    -- Strategy identifier:
    --   SMA_CROSSOVER | EMA_TREND | MOMENTUM | MEAN_REVERSION
    strategy_name TEXT NOT NULL,

    -- Exact parameter values used, e.g.:
    --   {"fast_window": 20, "slow_window": 50}
    --   {"lookback": 20}
    --   {"window": 20, "threshold": 0.02}
    -- Different configs of the same strategy are separate rows.
    parameters JSONB NOT NULL,

    -- Signal value: strictly one of -1, 0, or 1
    signal INTEGER NOT NULL
        CHECK (signal IN (-1, 0, 1)),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Idempotency: same strategy run → same row
    CONSTRAINT unique_strategy_signal
        UNIQUE (asset_id, date, strategy_name, parameters)
);

CREATE INDEX IF NOT EXISTS idx_strategy_signals_asset_date
    ON strategy_signals(asset_id, date);

CREATE INDEX IF NOT EXISTS idx_strategy_signals_strategy
    ON strategy_signals(strategy_name);

CREATE INDEX IF NOT EXISTS idx_strategy_signals_date
    ON strategy_signals(date);
