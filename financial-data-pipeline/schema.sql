-- =============================================================
-- Financial Data Pipeline  –  Database Schema
-- Run once in your Supabase SQL editor before running ingest.py
-- =============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------
-- assets
-- Master record for each tracked instrument
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ticker / symbol used throughout the pipeline
    symbol TEXT NOT NULL UNIQUE,

    -- Human-readable name
    name TEXT NOT NULL,

    -- Instrument class
    asset_type TEXT NOT NULL
        CHECK (
            asset_type IN (
                'COMMODITY',
                'CRYPTOCURRENCY',
                'EQUITY'
            )
        ),

    -- Data provider name (e.g. "Nasdaq Data Link")
    source TEXT NOT NULL,

    -- Provider-specific dataset identifier (e.g. "LBMA/GOLD")
    source_dataset TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------
-- market_prices
-- Normalised OHLCV rows; one row per (asset, trading date)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_prices (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    asset_id UUID NOT NULL
        REFERENCES assets(id)
        ON DELETE CASCADE,

    date DATE NOT NULL,

    open   NUMERIC,
    high   NUMERIC,
    low    NUMERIC,
    close  NUMERIC,
    volume NUMERIC,

    -- Data provider name
    source TEXT NOT NULL,

    -- Provider-specific dataset identifier
    source_dataset TEXT NOT NULL,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate (asset, date) rows; enables safe UPSERT
    CONSTRAINT unique_asset_date
        UNIQUE (asset_id, date)
);

-- -----------------------------------------------------------
-- ingestion_runs
-- Audit log; one record per asset per pipeline execution
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    asset_id UUID
        REFERENCES assets(id)
        ON DELETE SET NULL,

    source TEXT NOT NULL,

    source_dataset TEXT NOT NULL,

    requested_start_date DATE,
    requested_end_date   DATE,

    rows_downloaded       INTEGER NOT NULL DEFAULT 0,
    rows_after_cleaning   INTEGER NOT NULL DEFAULT 0,
    rows_rejected         INTEGER NOT NULL DEFAULT 0,
    rows_inserted         INTEGER NOT NULL DEFAULT 0,

    status TEXT NOT NULL
        CHECK (
            status IN (
                'RUNNING',
                'SUCCESS',
                'SUCCESS_WITH_WARNINGS',
                'FAILED'
            )
        ),

    error_message TEXT,

    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- -----------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_market_prices_asset_date
    ON market_prices(asset_id, date);

CREATE INDEX IF NOT EXISTS idx_market_prices_date
    ON market_prices(date);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_asset
    ON ingestion_runs(asset_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_started_at
    ON ingestion_runs(started_at);
