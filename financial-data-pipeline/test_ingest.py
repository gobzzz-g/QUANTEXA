"""
Tests for the Financial Data Ingestion Pipeline.

Run with:
    pytest test_ingest.py -v

These tests exercise the pure-Python transformation functions
(clean_data, validate_data, normalize_data) without requiring
network access or a live Supabase instance.
"""

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers to build test DataFrames
# ---------------------------------------------------------------------------


def _make_df(**overrides) -> pd.DataFrame:
    """
    Return a minimal, valid OHLCV DataFrame.
    Override individual columns by passing kwargs.
    """
    base = {
        "date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        "open":   [100.0, 101.0, 102.0],
        "high":   [110.0, 111.0, 112.0],
        "low":    [ 90.0,  91.0,  92.0],
        "close":  [105.0, 106.0, 107.0],
        "volume": [1000.0, 1100.0, 1200.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# Import the functions under test
# ---------------------------------------------------------------------------

from ingest import clean_data, normalize_data, validate_data, ASSETS


# ===========================================================================
# 1. clean_data – duplicate removal
# ===========================================================================

class TestCleanDataDuplicateRemoval:
    def test_removes_exact_duplicate_rows(self):
        """Exact duplicate rows must be dropped and counted."""
        row = {"date": "2024-01-02", "Open": 100.0, "High": 110.0,
               "Low": 90.0, "Close": 105.0, "Volume": 1000.0}
        df = pd.DataFrame([row, row, row])  # 3 identical rows

        clean_df, report = clean_data(df, "TestAsset")

        assert len(clean_df) == 1, "Only one row should remain after dedup"
        assert report["duplicate_rows_removed"] == 2

    def test_no_duplicates_unchanged(self):
        """A frame with no duplicates should not shrink."""
        df = pd.DataFrame([
            {"date": "2024-01-02", "Open": 100.0, "High": 110.0, "Low": 90.0,  "Close": 105.0, "Volume": 1000.0},
            {"date": "2024-01-03", "Open": 101.0, "High": 111.0, "Low": 91.0,  "Close": 106.0, "Volume": 1100.0},
        ])

        clean_df, report = clean_data(df, "TestAsset")

        assert len(clean_df) == 2
        assert report["duplicate_rows_removed"] == 0


# ===========================================================================
# 2. clean_data – missing value detection
# ===========================================================================

class TestCleanDataMissingValues:
    def test_detects_null_close(self):
        """Missing close prices must be reported in the cleaning report."""
        df = pd.DataFrame([
            {"date": "2024-01-02", "Open": 100.0, "High": 110.0, "Low": 90.0, "Close": None,  "Volume": 1000.0},
            {"date": "2024-01-03", "Open": 101.0, "High": 111.0, "Low": 91.0, "Close": 106.0, "Volume": 1100.0},
        ])

        _, report = clean_data(df, "TestAsset")

        assert "close" in report["missing_values_detected"]
        assert report["missing_values_detected"]["close"] == 1

    def test_detects_null_volume(self):
        """Missing volume must also be reported."""
        df = pd.DataFrame([
            {"date": "2024-01-02", "Open": 100.0, "High": 110.0, "Low": 90.0, "Close": 105.0, "Volume": None},
        ])

        _, report = clean_data(df, "TestAsset")

        assert "volume" in report["missing_values_detected"]

    def test_does_not_forward_fill_prices(self):
        """NaN prices must remain NaN – the pipeline must not silently impute."""
        df = pd.DataFrame([
            {"date": "2024-01-02", "Open": 100.0, "High": 110.0, "Low": 90.0, "Close": None,  "Volume": 1000.0},
            {"date": "2024-01-03", "Open": 101.0, "High": 111.0, "Low": 91.0, "Close": 106.0, "Volume": 1100.0},
        ])

        clean_df, _ = clean_data(df, "TestAsset")

        # Row 0 close should still be NaN
        close_values = clean_df["close"].tolist()
        assert close_values[0] is None or (
            isinstance(close_values[0], float) and math.isnan(close_values[0])
        ), "Null close must not be filled"


# ===========================================================================
# 3. validate_data – OHLC constraint checks
# ===========================================================================

class TestValidateDataOHLC:
    def _run_validation(self, df: pd.DataFrame):
        return validate_data(df, "TestAsset", "2020-01-01", "2026-12-31")

    def test_valid_ohlc_passes(self):
        """Rows satisfying all OHLC constraints must not be rejected."""
        df = _make_df()
        valid_df, report = self._run_validation(df)
        assert report["rows_rejected"] == 0
        assert len(valid_df) == 3

    def test_high_less_than_low_rejected(self):
        """A row where high < low violates OHLC and must be rejected."""
        df = _make_df(
            high=[50.0, 111.0, 112.0],
            low =[90.0,  91.0,  92.0],
        )
        _, report = self._run_validation(df)
        assert report["invalid_ohlc_rows"] >= 1

    def test_high_less_than_close_rejected(self):
        """high < close is an invalid OHLC relationship."""
        df = _make_df(
            high =[80.0, 111.0, 112.0],   # row 0: high=80, close=105 → invalid
            close=[105.0, 106.0, 107.0],
        )
        _, report = self._run_validation(df)
        assert report["invalid_ohlc_rows"] >= 1

    def test_low_greater_than_open_rejected(self):
        """low > open violates OHLC constraints."""
        df = _make_df(
            low =[200.0, 91.0, 92.0],   # row 0: low=200, open=100 → invalid
        )
        _, report = self._run_validation(df)
        assert report["invalid_ohlc_rows"] >= 1


# ===========================================================================
# 4. clean_data – negative price detection
# ===========================================================================

class TestCleanDataNegativePrices:
    def test_detects_negative_close(self):
        """Negative close prices must be flagged in the cleaning report."""
        df = pd.DataFrame([
            {"date": "2024-01-02", "Open": 100.0, "High": 110.0, "Low": 90.0, "Close": -5.0, "Volume": 1000.0},
        ])

        _, report = clean_data(df, "TestAsset")

        assert report["negative_price_rows"] >= 1

    def test_valid_prices_not_flagged(self):
        """All-positive prices must not produce a negative-price warning."""
        df = pd.DataFrame([
            {"date": "2024-01-02", "Open": 100.0, "High": 110.0, "Low": 90.0, "Close": 105.0, "Volume": 1000.0},
        ])

        _, report = clean_data(df, "TestAsset")

        assert report["negative_price_rows"] == 0


# ===========================================================================
# 5. normalize_data – column mapping
# ===========================================================================

class TestNormalizeData:
    def _gold_asset(self) -> dict:
        """Return the Gold asset config dict."""
        return next(a for a in ASSETS if a["key"] == "gold")

    def test_output_has_required_columns(self):
        """Normalized DataFrame must have all canonical output columns."""
        df = _make_df()
        asset = self._gold_asset()

        normalized = normalize_data(df, asset)

        required = {"asset", "asset_type", "date", "open", "high",
                    "low", "close", "volume", "source", "source_dataset"}
        assert required.issubset(set(normalized.columns))

    def test_asset_type_set_correctly(self):
        """Gold must be labelled COMMODITY."""
        df = _make_df()
        asset = self._gold_asset()

        normalized = normalize_data(df, asset)

        assert (normalized["asset_type"] == "COMMODITY").all()

    def test_symbol_set_correctly(self):
        """Gold symbol must be 'GOLD'."""
        df = _make_df()
        asset = self._gold_asset()

        normalized = normalize_data(df, asset)

        assert (normalized["asset"] == "GOLD").all()

    def test_source_set_to_yahoo(self):
        """source column must reference Yahoo Finance."""
        df = _make_df()
        asset = self._gold_asset()

        normalized = normalize_data(df, asset)

        assert (normalized["source"] == "Yahoo Finance").all()

    def test_row_count_preserved(self):
        """Normalization must not add or drop rows."""
        df = _make_df()
        asset = self._gold_asset()

        normalized = normalize_data(df, asset)

        assert len(normalized) == len(df)


# ===========================================================================
# 6. validate_data – duplicate date prevention
# ===========================================================================

class TestValidateDataDuplicateDates:
    def test_duplicate_dates_rejected(self):
        """Duplicate (asset, date) entries should be caught at validation."""
        df = _make_df(
            date=[date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 3)],  # row 0 and 1 share the same date
        )

        _, report = validate_data(df, "TestAsset", "2020-01-01", "2026-12-31")

        assert report["duplicate_date_rows"] >= 1
        assert report["rows_rejected"] >= 1

    def test_unique_dates_pass(self):
        """Frame with all-unique dates must have zero duplicate-date rejections."""
        df = _make_df()

        _, report = validate_data(df, "TestAsset", "2020-01-01", "2026-12-31")

        assert report["duplicate_date_rows"] == 0


# ===========================================================================
# 7. validate_data – negative price rejection
# ===========================================================================

class TestValidateDataNegativePrices:
    def test_negative_close_rejected(self):
        """Rows with negative close prices must be rejected by the validator."""
        df = _make_df(
            close=[-5.0, 106.0, 107.0],
        )

        _, report = validate_data(df, "TestAsset", "2020-01-01", "2026-12-31")

        # A negative close either triggers the OHLC check or the negative-price check.
        total_price_rejections = (
            report["invalid_ohlc_rows"] + report["negative_price_rows"]
        )
        assert total_price_rejections >= 1

    def test_negative_volume_rejected(self):
        """Rows with negative volume must be rejected."""
        df = _make_df(volume=[-500.0, 1100.0, 1200.0])

        _, report = validate_data(df, "TestAsset", "2020-01-01", "2026-12-31")

        assert report["negative_volume_rows"] >= 1
        assert report["rows_rejected"] >= 1
