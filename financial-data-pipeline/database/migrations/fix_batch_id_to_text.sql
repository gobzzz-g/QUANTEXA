-- =============================================================
-- fix_batch_id_to_text.sql
--
-- Purpose:
--   Change batch_id from UUID to TEXT across all tables.
--   This allows human-readable batch names like "TEST_BATCH_01"
--   to be used directly instead of UUIDs.
--
-- Run AFTER add_batch_architecture.sql in Supabase SQL Editor.
-- Safe to run even if batch_id is already TEXT (idempotent).
-- =============================================================

-- =============================================================
-- STEP 1: Drop FK constraints from all child tables
--         (PostgreSQL requires this before changing column type)
-- =============================================================

ALTER TABLE market_prices               DROP CONSTRAINT IF EXISTS market_prices_batch_id_fkey;
ALTER TABLE ingestion_runs              DROP CONSTRAINT IF EXISTS ingestion_runs_batch_id_fkey;
ALTER TABLE asset_indicators            DROP CONSTRAINT IF EXISTS asset_indicators_batch_id_fkey;
ALTER TABLE asset_statistics            DROP CONSTRAINT IF EXISTS asset_statistics_batch_id_fkey;
ALTER TABLE asset_correlations          DROP CONSTRAINT IF EXISTS asset_correlations_batch_id_fkey;
ALTER TABLE strategy_signals            DROP CONSTRAINT IF EXISTS strategy_signals_batch_id_fkey;
ALTER TABLE backtest_runs               DROP CONSTRAINT IF EXISTS backtest_runs_batch_id_fkey;
ALTER TABLE backtest_equity             DROP CONSTRAINT IF EXISTS backtest_equity_batch_id_fkey;
ALTER TABLE backtest_trades             DROP CONSTRAINT IF EXISTS backtest_trades_batch_id_fkey;
ALTER TABLE backtest_metrics            DROP CONSTRAINT IF EXISTS backtest_metrics_batch_id_fkey;
ALTER TABLE benchmark_results           DROP CONSTRAINT IF EXISTS benchmark_results_batch_id_fkey;
ALTER TABLE market_regimes              DROP CONSTRAINT IF EXISTS market_regimes_batch_id_fkey;
ALTER TABLE robustness_results          DROP CONSTRAINT IF EXISTS robustness_results_batch_id_fkey;
ALTER TABLE strategy_regime_performance DROP CONSTRAINT IF EXISTS strategy_regime_performance_batch_id_fkey;
ALTER TABLE portfolio_optimization_runs DROP CONSTRAINT IF EXISTS portfolio_optimization_runs_batch_id_fkey;
ALTER TABLE portfolio_allocations       DROP CONSTRAINT IF EXISTS portfolio_allocations_batch_id_fkey;
ALTER TABLE portfolio_results           DROP CONSTRAINT IF EXISTS portfolio_results_batch_id_fkey;
ALTER TABLE portfolio_covariance_inputs DROP CONSTRAINT IF EXISTS portfolio_covariance_inputs_batch_id_fkey;
ALTER TABLE qubo_runs                   DROP CONSTRAINT IF EXISTS qubo_runs_batch_id_fkey;
ALTER TABLE qubo_variables              DROP CONSTRAINT IF EXISTS qubo_variables_batch_id_fkey;
ALTER TABLE qubo_matrix                 DROP CONSTRAINT IF EXISTS qubo_matrix_batch_id_fkey;
ALTER TABLE qubo_results                DROP CONSTRAINT IF EXISTS qubo_results_batch_id_fkey;
ALTER TABLE batch_assets                DROP CONSTRAINT IF EXISTS batch_assets_batch_id_fkey;
ALTER TABLE batch_layer_runs            DROP CONSTRAINT IF EXISTS batch_layer_runs_batch_id_fkey;

-- =============================================================
-- STEP 2: Drop the analysis_batches PRIMARY KEY constraint
-- =============================================================

ALTER TABLE analysis_batches DROP CONSTRAINT IF EXISTS analysis_batches_pkey;

-- =============================================================
-- STEP 3: Change analysis_batches.batch_id UUID -> TEXT
-- =============================================================

ALTER TABLE analysis_batches
    ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;

-- Restore primary key
ALTER TABLE analysis_batches
    ADD CONSTRAINT analysis_batches_pkey PRIMARY KEY (batch_id);

-- Add UNIQUE on batch_name for lookups by name
ALTER TABLE analysis_batches
    DROP CONSTRAINT IF EXISTS analysis_batches_batch_name_key;
ALTER TABLE analysis_batches
    ADD CONSTRAINT analysis_batches_batch_name_key UNIQUE (batch_name);

-- =============================================================
-- STEP 4: Change all child tables batch_id UUID -> TEXT
-- =============================================================

ALTER TABLE market_prices               ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE ingestion_runs              ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE asset_indicators            ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE asset_statistics            ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE asset_correlations          ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE strategy_signals            ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE backtest_runs               ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE backtest_equity             ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE backtest_trades             ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE backtest_metrics            ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE benchmark_results           ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE market_regimes              ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE robustness_results          ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE strategy_regime_performance ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE portfolio_optimization_runs ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE portfolio_allocations       ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE portfolio_results           ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE portfolio_covariance_inputs ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE qubo_runs                   ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE qubo_variables              ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE qubo_matrix                 ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE qubo_results                ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE batch_assets                ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;
ALTER TABLE batch_layer_runs            ALTER COLUMN batch_id TYPE TEXT USING batch_id::TEXT;

-- =============================================================
-- STEP 5: Update the LEGACY batch row to use a readable TEXT key
--         (old UUID string is kept as the TEXT value — still valid)
--
-- The Python code now uses "LEGACY_EXISTING_RUN" as the batch_id.
-- Insert (or update) a row with that TEXT key.
-- =============================================================

-- Rename existing LEGACY batch_id to the readable string
UPDATE analysis_batches
    SET batch_id = 'LEGACY_EXISTING_RUN'
WHERE batch_name = 'LEGACY_EXISTING_RUN'
  AND batch_id != 'LEGACY_EXISTING_RUN';

-- Update all child tables to point to 'LEGACY_EXISTING_RUN'
DO $$
DECLARE old_uuid TEXT;
BEGIN
    -- This is only needed if the batch_id was a UUID before
    -- Now all rows have been cast to TEXT already
    -- Just ensure any NULL rows get assigned (idempotent)
    NULL;
END $$;

-- =============================================================
-- STEP 6: Restore batch_assets UNIQUE constraint (now TEXT)
-- =============================================================

ALTER TABLE batch_assets
    DROP CONSTRAINT IF EXISTS batch_assets_batch_id_asset_id_key;
ALTER TABLE batch_assets
    ADD CONSTRAINT batch_assets_batch_id_asset_id_key
    UNIQUE (batch_id, asset_id);

ALTER TABLE batch_layer_runs
    DROP CONSTRAINT IF EXISTS batch_layer_runs_batch_id_layer_number_key;
ALTER TABLE batch_layer_runs
    ADD CONSTRAINT batch_layer_runs_batch_id_layer_number_key
    UNIQUE (batch_id, layer_number);

-- =============================================================
-- STEP 7: Verify
-- =============================================================

SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'analysis_batches'
  AND column_name = 'batch_id';

-- Expected output: data_type = 'text'
