-- =============================================================
-- fix_missing_constraints.sql
--
-- Adds missing unique constraints that backtest_engine.py
-- requires for ON CONFLICT upserts.
--
-- Run in Supabase SQL Editor after fix_batch_id_to_text.sql
-- =============================================================

-- benchmark_results: required by save_benchmark()
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'unique_batch_benchmark'
          AND conrelid = 'benchmark_results'::regclass
    ) THEN
        ALTER TABLE benchmark_results
            ADD CONSTRAINT unique_batch_benchmark
            UNIQUE (batch_id, asset_id, benchmark_name, start_date, end_date, initial_capital);
    END IF;
END $$;

-- backtest_metrics: required by save_metrics()
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'unique_backtest_metric'
          AND conrelid = 'backtest_metrics'::regclass
    ) THEN
        ALTER TABLE backtest_metrics
            ADD CONSTRAINT unique_backtest_metric
            UNIQUE (backtest_run_id, metric_name);
    END IF;
END $$;

-- Verify
SELECT conname, conrelid::regclass
FROM pg_constraint
WHERE conname IN ('unique_batch_benchmark', 'unique_backtest_metric');
