"""
Unit tests for the Quantitative Analysis Engine (Layer 2).

All tests use small, deterministic, in-memory DataFrames.
No network access or Supabase connection is required.

Run with:
    pytest test_quant_engine.py -v
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from quant_engine import (
    ANNUALIZATION_FACTOR,
    calculate_asset_statistics,
    calculate_correlations,
    calculate_max_drawdown,
    calculate_moving_averages,
    calculate_returns,
    calculate_volatility,
    validate_calculations,
)

# ---------------------------------------------------------------------------
# Sample data builders
# ---------------------------------------------------------------------------


def _make_df(
    asset_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
    symbol: str = "TEST",
    asset_type: str = "EQUITY",
    closes: list[float] | None = None,
    start_date: date = date(2020, 1, 2),
) -> pd.DataFrame:
    """
    Build a minimal single-asset DataFrame matching the schema returned by
    load_market_data().  ``closes`` is used for both open and close for
    simplicity; tests only inspect the close column.
    """
    if closes is None:
        closes = [100.0, 105.0, 102.0, 108.0, 103.0]

    n = len(closes)
    dates = [start_date + timedelta(days=i) for i in range(n)]

    return pd.DataFrame(
        {
            "asset_id":   [asset_id] * n,
            "symbol":     [symbol] * n,
            "asset_type": [asset_type] * n,
            "date":       dates,
            "open":       closes,
            "high":       [c * 1.02 for c in closes],
            "low":        [c * 0.98 for c in closes],
            "close":      [float(c) for c in closes],
            "volume":     [1_000_000.0] * n,
        }
    )


def _make_two_asset_df() -> pd.DataFrame:
    """Build a two-asset DataFrame with shared dates for correlation tests."""
    a1 = "aaaaaaaa-0000-0000-0000-000000000001"
    a2 = "bbbbbbbb-0000-0000-0000-000000000002"
    # 60 observations so rolling-30 and rolling-60 are reachable
    n = 60
    start = date(2020, 1, 2)
    dates = [start + timedelta(days=i) for i in range(n)]

    rng = np.random.default_rng(seed=42)
    closes1 = (100 * np.cumprod(1 + rng.normal(0.001, 0.02, n))).tolist()
    closes2 = (100 * np.cumprod(1 + rng.normal(0.001, 0.02, n))).tolist()

    rows = []
    for dt, c1, c2 in zip(dates, closes1, closes2):
        for aid, sym, cl in [(a1, "AAA", c1), (a2, "BBB", c2)]:
            rows.append(
                {
                    "asset_id": aid,
                    "symbol": sym,
                    "asset_type": "EQUITY",
                    "date": dt,
                    "open": cl,
                    "high": cl * 1.01,
                    "low": cl * 0.99,
                    "close": float(cl),
                    "volume": 1_000_000.0,
                }
            )

    return pd.DataFrame(rows).sort_values(["asset_id", "date"]).reset_index(drop=True)


# ===========================================================================
# 1. Daily return calculation
# ===========================================================================


class TestDailyReturn:
    def test_first_return_is_nan(self):
        """First observation has no prior price so daily_return must be NaN."""
        df = _make_df(closes=[100.0, 105.0])
        df = calculate_returns(df)
        assert pd.isna(df["daily_return"].iloc[0])

    def test_return_formula(self):
        """daily_return = (close_t / close_{t-1}) - 1."""
        df = _make_df(closes=[100.0, 110.0, 99.0])
        df = calculate_returns(df)

        assert abs(df["daily_return"].iloc[1] - 0.10) < 1e-10
        expected = (99.0 / 110.0) - 1.0
        assert abs(df["daily_return"].iloc[2] - expected) < 1e-10

    def test_no_cross_asset_contamination(self):
        """
        The return on the first trading day of asset B must be NaN even if
        asset A has data immediately before that date.
        """
        a1 = "aaaaaaaa-0000-0000-0000-000000000001"
        a2 = "bbbbbbbb-0000-0000-0000-000000000002"

        df = pd.concat(
            [
                _make_df(asset_id=a1, closes=[100.0, 110.0], start_date=date(2020, 1, 2)),
                _make_df(asset_id=a2, closes=[200.0, 220.0], start_date=date(2020, 1, 3)),
            ],
            ignore_index=True,
        )
        df = calculate_returns(df)

        # First row of asset B (2020-01-03) must be NaN
        b_first = df[(df["asset_id"] == a2) & (df["date"] == date(2020, 1, 3))][
            "daily_return"
        ]
        assert b_first.notna().sum() == 0, "First return of asset B must be NaN"


# ===========================================================================
# 2. SMA calculation
# ===========================================================================


class TestSMA:
    def test_sma_nan_before_window_full(self):
        """SMA_20 must be NaN for the first 19 rows (look-ahead bias check)."""
        closes = list(range(1, 26))  # 25 data points
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        sma20 = df["sma_20"].tolist()
        # Positions 0–18 (first 19) must be NaN
        assert all(pd.isna(sma20[i]) for i in range(19)), (
            "SMA_20 must be NaN for observations 0–18"
        )
        # Position 19 (20th row) must be non-NaN
        assert not pd.isna(sma20[19]), "SMA_20 must be valid at observation 20"

    def test_sma_value_correct(self):
        """SMA of a constant price series equals that constant."""
        closes = [50.0] * 25
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        valid_sma = df["sma_20"].dropna()
        assert (valid_sma == 50.0).all(), "SMA of constant series must equal the constant"

    def test_sma50_nan_before_50_rows(self):
        """SMA_50 must remain NaN until 50 observations are available."""
        closes = list(range(1, 55))  # 54 data points
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        sma50 = df["sma_50"].tolist()
        assert all(pd.isna(sma50[i]) for i in range(49))
        assert not pd.isna(sma50[49])

    def test_sma200_all_nan_when_insufficient(self):
        """SMA_200 must be entirely NaN when fewer than 200 rows exist."""
        closes = [100.0] * 50  # only 50 rows
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        assert df["sma_200"].isna().all(), (
            "SMA_200 must be all-NaN when fewer than 200 observations are available"
        )


# ===========================================================================
# 3. EMA calculation
# ===========================================================================


class TestEMA:
    def test_ema_constant_series(self):
        """EMA of a constant price series equals that constant."""
        closes = [75.0] * 30
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        # Every EMA value should equal 75.0 (constant input)
        for col in ["ema_20", "ema_50"]:
            vals = df[col].dropna()
            assert (vals.round(8) == 75.0).all(), (
                f"{col} of constant series must equal the constant"
            )

    def test_ema_first_value_equals_first_close(self):
        """
        With adjust=False, the EMA seed (first value) equals the first close price.
        """
        closes = [100.0, 200.0, 300.0]
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        assert abs(df["ema_20"].iloc[0] - 100.0) < 1e-8, (
            "First EMA value must equal the first close price"
        )

    def test_ema_defined_from_first_obs(self):
        """EMA must have non-NaN values from the very first observation."""
        closes = [10.0, 20.0, 30.0]
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        assert df["ema_20"].notna().all(), (
            "EMA should be defined from the first observation"
        )


# ===========================================================================
# 4. Volatility calculation
# ===========================================================================


class TestVolatility:
    def test_volatility_non_negative(self):
        """All non-NaN volatility values must be >= 0."""
        closes = [100 * (1 + 0.001 * i + 0.005 * (i % 3)) for i in range(100)]
        df = _make_df(closes=closes)
        df = calculate_returns(df)
        df = calculate_volatility(df)

        for col in ["volatility_20", "volatility_60", "volatility_252"]:
            vals = df[col].dropna()
            assert (vals >= 0).all(), f"{col} has negative values"

    def test_volatility_nan_before_window(self):
        """volatility_20 must be NaN for the first 19 rows."""
        closes = list(range(1, 50))
        df = _make_df(closes=closes)
        df = calculate_returns(df)
        df = calculate_volatility(df)

        vol20 = df["volatility_20"].tolist()
        # daily_return is NaN for row 0; rolling std needs 20 returns.
        # Row 0: NaN return → Row 20 (21st) is first valid vol_20
        assert all(pd.isna(vol20[i]) for i in range(20))
        assert not pd.isna(vol20[20])

    def test_zero_volatility_constant_returns(self):
        """A series with identical close prices produces zero volatility."""
        closes = [50.0] * 50
        df = _make_df(closes=closes)
        df = calculate_returns(df)
        df = calculate_volatility(df)

        valid_vol = df["volatility_20"].dropna()
        assert (valid_vol.round(10) == 0.0).all(), (
            "Constant price series must have zero volatility"
        )


# ===========================================================================
# 5. Maximum drawdown calculation
# ===========================================================================


class TestMaxDrawdown:
    def _dates(self, n: int) -> np.ndarray:
        return np.array(
            [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]
        )

    def test_known_drawdown(self):
        """100 → 150 → 75: drawdown = (75/150) - 1 = -0.5."""
        close = np.array([100.0, 150.0, 75.0])
        dates = self._dates(3)
        result = calculate_max_drawdown(close, dates)

        assert abs(result["max_drawdown"] - (-0.5)) < 1e-9
        assert result["max_drawdown_start_date"] == date(2020, 1, 2)  # peak at 150
        assert result["max_drawdown_trough_date"] == date(2020, 1, 3)  # trough at 75

    def test_no_recovery(self):
        """If price never recovers to peak, recovery_date must be None."""
        close = np.array([100.0, 150.0, 75.0, 140.0])  # 140 < 150 peak
        dates = self._dates(4)
        result = calculate_max_drawdown(close, dates)

        assert result["max_drawdown_recovery_date"] is None

    def test_with_recovery(self):
        """If price recovers to peak, recovery_date must be recorded."""
        close = np.array([100.0, 150.0, 75.0, 160.0])  # 160 >= 150 peak
        dates = self._dates(4)
        result = calculate_max_drawdown(close, dates)

        assert result["max_drawdown_recovery_date"] == date(2020, 1, 4)

    def test_monotone_increase_no_drawdown(self):
        """Monotonically increasing prices have zero drawdown."""
        close = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        dates = self._dates(5)
        result = calculate_max_drawdown(close, dates)

        assert abs(result["max_drawdown"]) < 1e-9

    def test_drawdown_always_le_zero(self):
        """Max drawdown must always be <= 0."""
        rng = np.random.default_rng(seed=7)
        close = np.abs(rng.normal(100, 20, 200))
        dates = self._dates(200)
        result = calculate_max_drawdown(close, dates)

        assert result["max_drawdown"] <= 0.0, (
            f"Max drawdown must be <= 0 but got {result['max_drawdown']}"
        )


# ===========================================================================
# 6. Correlation calculation
# ===========================================================================


class TestCorrelations:
    def test_identical_series_correlation_one(self):
        """
        Two identical (non-constant) return series must have rolling
        correlation = 1.0.  A pure geometric series (1.01^i) produces
        constant returns with undefined correlation, so we use a random
        walk instead to guarantee non-zero variance.
        """
        a1 = "aaaaaaaa-0000-0000-0000-000000000001"
        a2 = "bbbbbbbb-0000-0000-0000-000000000002"

        # Build a random-walk price series with genuine return variability
        rng = np.random.default_rng(seed=99)
        returns = rng.normal(0.001, 0.02, 50)
        closes = (100.0 * np.cumprod(1 + returns)).tolist()

        df = pd.concat(
            [
                _make_df(asset_id=a1, symbol="AAA", closes=closes),
                _make_df(asset_id=a2, symbol="BBB", closes=closes),  # identical
            ],
            ignore_index=True,
        ).sort_values(["asset_id", "date"]).reset_index(drop=True)

        df = calculate_returns(df)
        corr_df = calculate_correlations(df)

        # Filter for window_days=30
        w30 = corr_df[corr_df["window_days"] == 30]["correlation"].dropna()
        assert len(w30) > 0, "Expected correlation records for window=30"
        assert (w30.round(6) == 1.0).all(), (
            "Identical return series must have rolling correlation = 1.0"
        )

    def test_pair_ordering(self):
        """asset_1_id must always be < asset_2_id (UUID string comparison)."""
        df = _make_two_asset_df()
        df = calculate_returns(df)
        corr_df = calculate_correlations(df)

        if not corr_df.empty:
            assert (corr_df["asset_1_id"] < corr_df["asset_2_id"]).all(), (
                "asset_1_id must always be lexicographically smaller than asset_2_id"
            )

    def test_correlation_in_range(self):
        """All correlation values must be in [-1.0, +1.0]."""
        df = _make_two_asset_df()
        df = calculate_returns(df)
        corr_df = calculate_correlations(df)

        if not corr_df.empty:
            c = corr_df["correlation"].dropna()
            assert ((c >= -1.0 - 1e-9) & (c <= 1.0 + 1e-9)).all(), (
                "Correlation values must be in [-1, 1]"
            )

    def test_no_self_correlation(self):
        """asset_1_id must never equal asset_2_id."""
        df = _make_two_asset_df()
        df = calculate_returns(df)
        corr_df = calculate_correlations(df)

        if not corr_df.empty:
            assert (corr_df["asset_1_id"] != corr_df["asset_2_id"]).all()


# ===========================================================================
# 7. No look-ahead bias
# ===========================================================================


class TestNoLookahead:
    def test_sma20_nan_until_20_obs(self):
        """
        SMA_20 must be NaN for the first 19 rows regardless of the values.
        Any non-NaN value before position 19 would indicate look-ahead bias.
        """
        closes = [float(i + 1) for i in range(30)]
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        for i in range(19):
            assert pd.isna(df["sma_20"].iloc[i]), (
                f"SMA_20 at position {i} must be NaN (look-ahead bias check)"
            )
        assert not pd.isna(df["sma_20"].iloc[19])

    def test_sma20_value_matches_window_data(self):
        """
        Verify that SMA_20 at position 19 equals the mean of exactly the first
        20 close prices, not any future data.
        """
        closes = list(range(1, 31))  # [1, 2, ..., 30]
        df = _make_df(closes=closes)
        df = calculate_moving_averages(df)

        expected = sum(range(1, 21)) / 20  # mean([1, ..., 20]) = 10.5
        actual = df["sma_20"].iloc[19]
        assert abs(actual - expected) < 1e-9, (
            f"SMA_20 at position 19 = {actual}, expected {expected}"
        )

    def test_volatility_nan_before_window(self):
        """volatility_60 must be NaN for the first 60 rows of returns."""
        closes = list(range(1, 100))
        df = _make_df(closes=closes)
        df = calculate_returns(df)
        df = calculate_volatility(df)

        # Row 0: NaN return; rows 1-59: fewer than 60 returns → NaN
        vol60 = df["volatility_60"].tolist()
        assert all(pd.isna(vol60[i]) for i in range(60))


# ===========================================================================
# 8. Duplicate prevention via validate_calculations
# ===========================================================================


class TestValidation:
    def _build_valid_df(self) -> pd.DataFrame:
        """Build a minimal valid indicators DataFrame."""
        closes = [100.0 * (1.01 ** i) for i in range(30)]
        df = _make_df(closes=closes)
        df = calculate_returns(df)
        df = calculate_moving_averages(df)
        df = calculate_volatility(df)
        return df

    def test_valid_df_passes(self):
        """A correctly computed DataFrame must pass all validation checks."""
        df = self._build_valid_df()
        stats = calculate_asset_statistics(df, risk_free_rate=0.0)
        corr_df = pd.DataFrame(
            columns=["asset_1_id", "asset_2_id", "date", "window_days", "correlation"]
        )
        # Should not raise
        validate_calculations(df, stats, corr_df)

    def test_duplicate_dates_rejected(self):
        """
        validate_calculations must raise ValueError when duplicate (asset, date)
        rows are present.  Depending on sort order, either the "duplicate" or
        the "not sorted" check fires first – both are correct responses.
        """
        df = self._build_valid_df()
        # Append a row with a date that already exists → triggers either the
        # sort check or the duplicate check depending on concat order.
        df_with_dup = pd.concat([df, df.iloc[[5]]], ignore_index=True)

        with pytest.raises(ValueError, match="duplicate|sorted|Duplicate|Sorted"):
            validate_calculations(df_with_dup, [], pd.DataFrame())

    def test_invalid_correlation_rejected(self):
        """A correlation outside [-1, 1] must be rejected."""
        df = self._build_valid_df()
        bad_corr = pd.DataFrame(
            [
                {
                    "asset_1_id": "aaa",
                    "asset_2_id": "bbb",
                    "date": "2020-01-10",
                    "window_days": 30,  # invalid correlation value test
                    "correlation": 1.5,  # invalid
                }
            ]
        )
        with pytest.raises(ValueError, match="outside"):
            validate_calculations(df, [], bad_corr)

    def test_negative_volatility_rejected(self):
        """Negative volatility values must be caught."""
        df = self._build_valid_df()
        df_bad = df.copy()
        df_bad.loc[df_bad["volatility_20"].notna(), "volatility_20"] = -0.01

        with pytest.raises(ValueError, match="[Nn]egative"):
            validate_calculations(df_bad, [], pd.DataFrame())

    def test_positive_max_drawdown_rejected(self):
        """Max drawdown > 0 is mathematically impossible and must be caught."""
        df = self._build_valid_df()
        stats = calculate_asset_statistics(df, risk_free_rate=0.0)
        # Artificially corrupt the max_drawdown
        for s in stats:
            s["max_drawdown"] = 0.05  # positive — impossible

        with pytest.raises(ValueError, match="[Mm]ax drawdown"):
            validate_calculations(df, stats, pd.DataFrame())

    def test_non_finite_return_rejected(self):
        """Non-finite (inf/nan-as-float) daily returns must be caught."""
        df = self._build_valid_df()
        df_bad = df.copy()
        # Set a non-NaN, non-finite return
        first_valid = df_bad["daily_return"].first_valid_index()
        df_bad.loc[first_valid, "daily_return"] = float("inf")

        with pytest.raises(ValueError, match="[Nn]on-finite"):
            validate_calculations(df_bad, [], pd.DataFrame())
