-- =============================================================
-- Batch Architecture Migration
-- add_batch_architecture.sql
--
-- Purpose:
--   1. Create batch tracking tables (analysis_batches, batch_assets,
--      batch_layer_runs).
--   2. Add batch_id column to all Layer 1-7 result tables.
--   3. Create a LEGACY batch for existing data.
--   4. Assign legacy batch_id to all existing NULL rows.
--   5. Fix unique constraints so multiple batches can coexist.
--   6. Add performance indexes on batch_id.
--
-- Safety guarantees:
--   - NO TABLE IS DROPPED.
--   - NO ROW IS DELETED.
--   - Existing data is preserved.
--   - Migration is idempotent (safe to re-run).
--
-- Run once in Supabase SQL Editor before running run_pipeline.py
-- =============================================================

-- =============================================================
-- STEP 1: Create parent batch tracking tables
-- =============================================================

CREATE TABLE IF NOT EXISTS analysis_batches (
    batch_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_name       TEXT NOT NULL,
    dataset_filename TEXT,
    dataset_hash     TEXT,          -- SHA-256 of uploaded CSV for dedup detection
    status           TEXT NOT NULL DEFAULT 'CREATED'
        CHECK (status IN ('CREATED','RUNNING','COMPLETED','FAILED')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    error_message    TEXT,
    config           JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS batch_assets (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id   UUID NOT NULL REFERENCES analysis_batches(batch_id) ON DELETE CASCADE,
    asset_id   UUID NOT NULL REFERENCES assets(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(batch_id, asset_id)
);

CREATE TABLE IF NOT EXISTS batch_layer_runs (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id       UUID NOT NULL REFERENCES analysis_batches(batch_id) ON DELETE CASCADE,
    layer_number   INT NOT NULL,
    layer_name     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'NOT_STARTED'
        CHECK (status IN ('NOT_STARTED','RUNNING','COMPLETED','FAILED')),
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    rows_processed BIGINT,
    error_message  TEXT,
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(batch_id, layer_number)
);

-- =============================================================
-- STEP 2: Add batch_id column to all Layer 1-7 result tables
-- =============================================================

-- Layer 1 tables
ALTER TABLE market_prices
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE ingestion_runs
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

-- Layer 2 tables
ALTER TABLE asset_indicators
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE asset_statistics
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE asset_correlations
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

-- Layer 3 tables
ALTER TABLE strategy_signals
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

-- Layer 4 tables
ALTER TABLE backtest_runs
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE backtest_equity
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE backtest_trades
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE backtest_metrics
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE benchmark_results
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

-- Layer 5 tables
ALTER TABLE market_regimes
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE robustness_results
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE strategy_regime_performance
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

-- Layer 6 tables
ALTER TABLE portfolio_optimization_runs
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE portfolio_allocations
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE portfolio_results
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE portfolio_covariance_inputs
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

-- Layer 7 tables
ALTER TABLE qubo_runs
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE qubo_variables
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE qubo_matrix
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

ALTER TABLE qubo_results
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES analysis_batches(batch_id);

-- =============================================================
-- STEP 3: Create the LEGACY batch for all existing data
-- =============================================================

DO $$
DECLARE
    legacy_id UUID;
BEGIN
    -- Only create once (idempotent)
    IF NOT EXISTS (
        SELECT 1 FROM analysis_batches WHERE batch_name = 'LEGACY_EXISTING_RUN'
    ) THEN
        INSERT INTO analysis_batches
            (batch_name, status, config)
        VALUES
            ('LEGACY_EXISTING_RUN', 'COMPLETED',
             '{"note": "Legacy data migrated automatically", "source": "Yahoo Finance"}'::jsonb)
        RETURNING batch_id INTO legacy_id;
    ELSE
        SELECT batch_id INTO legacy_id
        FROM analysis_batches WHERE batch_name = 'LEGACY_EXISTING_RUN';
    END IF;

    -- Assign legacy batch_id to all NULL rows in every result table
    -- Only touches rows where batch_id IS NULL (never overwrites existing non-null)

    UPDATE market_prices          SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE ingestion_runs         SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE asset_indicators       SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE asset_statistics       SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE asset_correlations     SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE strategy_signals       SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE backtest_runs          SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE backtest_equity        SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE backtest_trades        SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE backtest_metrics       SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE benchmark_results      SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE market_regimes         SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE robustness_results     SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE strategy_regime_performance SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE portfolio_optimization_runs SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE portfolio_allocations  SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE portfolio_results      SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE portfolio_covariance_inputs SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE qubo_runs              SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE qubo_variables         SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE qubo_matrix            SET batch_id = legacy_id WHERE batch_id IS NULL;
    UPDATE qubo_results           SET batch_id = legacy_id WHERE batch_id IS NULL;

    -- Also register legacy assets in batch_assets
    INSERT INTO batch_assets (batch_id, asset_id)
    SELECT legacy_id, id FROM assets
    ON CONFLICT (batch_id, asset_id) DO NOTHING;

END $$;

-- =============================================================
-- STEP 4: Fix unique constraints for multi-batch coexistence
-- =============================================================

-- market_prices: old UNIQUE(asset_id, date) → new UNIQUE(batch_id, asset_id, date)
DO $$
BEGIN
    -- Drop old constraint (the name from schema.sql is unique_asset_date)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'market_prices'
          AND constraint_name = 'unique_asset_date'
          AND constraint_type = 'UNIQUE'
    ) THEN
        ALTER TABLE market_prices DROP CONSTRAINT unique_asset_date;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'unique_batch_asset_date'
          AND conrelid = 'market_prices'::regclass
    ) THEN
        ALTER TABLE market_prices
            ADD CONSTRAINT unique_batch_asset_date
            UNIQUE (batch_id, asset_id, date);
    END IF;
END $$;

-- asset_indicators: find and fix unique constraint
DO $$
DECLARE
    con_name TEXT;
BEGIN
    SELECT constraint_name INTO con_name
    FROM information_schema.table_constraints
    WHERE table_name = 'asset_indicators'
      AND constraint_type = 'UNIQUE'
    LIMIT 1;

    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE asset_indicators DROP CONSTRAINT IF EXISTS %I', con_name);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'unique_batch_asset_indicator_date'
          AND conrelid = 'asset_indicators'::regclass
    ) THEN
        ALTER TABLE asset_indicators
            ADD CONSTRAINT unique_batch_asset_indicator_date
            UNIQUE (batch_id, asset_id, date);
    END IF;
END $$;

-- asset_statistics: fix unique constraint
DO $$
DECLARE
    con_name TEXT;
BEGIN
    SELECT constraint_name INTO con_name
    FROM information_schema.table_constraints
    WHERE table_name = 'asset_statistics'
      AND constraint_type = 'UNIQUE'
    LIMIT 1;

    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE asset_statistics DROP CONSTRAINT IF EXISTS %I', con_name);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'unique_batch_asset_stat'
          AND conrelid = 'asset_statistics'::regclass
    ) THEN
        ALTER TABLE asset_statistics
            ADD CONSTRAINT unique_batch_asset_stat
            UNIQUE (batch_id, asset_id, start_date, end_date);
    END IF;
END $$;

-- asset_correlations: fix unique constraint
DO $$
DECLARE
    con_name TEXT;
BEGIN
    SELECT constraint_name INTO con_name
    FROM information_schema.table_constraints
    WHERE table_name = 'asset_correlations'
      AND constraint_type = 'UNIQUE'
    LIMIT 1;

    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE asset_correlations DROP CONSTRAINT IF EXISTS %I', con_name);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'unique_batch_corr'
          AND conrelid = 'asset_correlations'::regclass
    ) THEN
        ALTER TABLE asset_correlations
            ADD CONSTRAINT unique_batch_corr
            UNIQUE (batch_id, asset_1_id, asset_2_id, date, window_days);
    END IF;
END $$;

-- strategy_signals: fix unique constraint
DO $$
DECLARE
    con_name TEXT;
BEGIN
    SELECT constraint_name INTO con_name
    FROM information_schema.table_constraints
    WHERE table_name = 'strategy_signals'
      AND constraint_type = 'UNIQUE'
    LIMIT 1;

    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE strategy_signals DROP CONSTRAINT IF EXISTS %I', con_name);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'unique_batch_signal'
          AND conrelid = 'strategy_signals'::regclass
    ) THEN
        ALTER TABLE strategy_signals
            ADD CONSTRAINT unique_batch_signal
            UNIQUE (batch_id, asset_id, date, strategy_name);
    END IF;
END $$;

-- portfolio_optimization_runs: no existing unique constraint (UUID PK only)
-- portfolio_covariance_inputs: old UNIQUE(run_id, asset_1_symbol, asset_2_symbol) is fine
--   because run_id already scopes to a batch

-- qubo_results: old UNIQUE(qubo_run_id, solver_name) is fine
-- qubo_variables: old UNIQUE(qubo_run_id, variable_index) is fine
-- qubo_matrix: old UNIQUE(qubo_run_id, row_index, col_index) is fine

-- portfolio_allocations: old UNIQUE(run_id, asset_id) is fine

-- =============================================================
-- STEP 5: Performance indexes on batch_id
-- =============================================================

CREATE INDEX IF NOT EXISTS idx_market_prices_batch
    ON market_prices(batch_id);

CREATE INDEX IF NOT EXISTS idx_market_prices_batch_asset_date
    ON market_prices(batch_id, asset_id, date);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_batch
    ON ingestion_runs(batch_id);

CREATE INDEX IF NOT EXISTS idx_asset_indicators_batch
    ON asset_indicators(batch_id);

CREATE INDEX IF NOT EXISTS idx_asset_indicators_batch_asset
    ON asset_indicators(batch_id, asset_id);

CREATE INDEX IF NOT EXISTS idx_asset_statistics_batch
    ON asset_statistics(batch_id);

CREATE INDEX IF NOT EXISTS idx_asset_correlations_batch
    ON asset_correlations(batch_id);

CREATE INDEX IF NOT EXISTS idx_strategy_signals_batch
    ON strategy_signals(batch_id);

CREATE INDEX IF NOT EXISTS idx_strategy_signals_batch_asset
    ON strategy_signals(batch_id, asset_id);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_batch
    ON backtest_runs(batch_id);

CREATE INDEX IF NOT EXISTS idx_backtest_equity_batch
    ON backtest_equity(batch_id);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_batch
    ON backtest_trades(batch_id);

CREATE INDEX IF NOT EXISTS idx_backtest_metrics_batch
    ON backtest_metrics(batch_id);

CREATE INDEX IF NOT EXISTS idx_benchmark_results_batch
    ON benchmark_results(batch_id);

CREATE INDEX IF NOT EXISTS idx_market_regimes_batch
    ON market_regimes(batch_id);

CREATE INDEX IF NOT EXISTS idx_robustness_results_batch
    ON robustness_results(batch_id);

CREATE INDEX IF NOT EXISTS idx_strategy_regime_performance_batch
    ON strategy_regime_performance(batch_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_optimization_runs_batch
    ON portfolio_optimization_runs(batch_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_allocations_batch
    ON portfolio_allocations(batch_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_results_batch
    ON portfolio_results(batch_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_covariance_inputs_batch
    ON portfolio_covariance_inputs(batch_id);

CREATE INDEX IF NOT EXISTS idx_qubo_runs_batch
    ON qubo_runs(batch_id);

CREATE INDEX IF NOT EXISTS idx_qubo_results_batch
    ON qubo_results(batch_id);

-- =============================================================
-- Verification query (run after migration to confirm)
-- =============================================================

-- SELECT
--     batch_name, status, created_at,
--     (SELECT COUNT(*) FROM market_prices WHERE batch_id = ab.batch_id)     AS prices,
--     (SELECT COUNT(*) FROM asset_indicators WHERE batch_id = ab.batch_id)  AS indicators,
--     (SELECT COUNT(*) FROM strategy_signals WHERE batch_id = ab.batch_id)  AS signals
-- FROM analysis_batches ab
-- ORDER BY created_at;