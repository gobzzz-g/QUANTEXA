"""
Unit tests for the Strategy Engine (Layer 3).

All tests use small, deterministic, in-memory DataFrames.
No Supabase connection is required.

Run with:
    pytest test_strategy_engine.py -v
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from strategy_engine import (
    generate_ema_trend_signals,
    generate_mean_reversion_signals,
    generate_momentum_signals,
    generate_sma_crossover_signals,
    validate_signals,
)

# ---------------------------------------------------------------------------
# Sample data builder
# ---------------------------------------------------------------------------

_AID_1 = "aaaaaaaa-0000-0000-0000-000000000001"
_AID_2 = "bbbbbbbb-0000-0000-0000-000000000002"


def _make_df(
    asset_id: str = _AID_1,
    symbol: str = "TEST",
    n: int = 10,
    close: list[float] | None = None,
    sma_20: list[float | None] | None = None,
    sma_50: list[float | None] | None = None,
    sma_200: list[float | None] | None = None,
    ema_20: list[float | None] | None = None,
    ema_50: list[float | None] | None = None,
    daily_return: list[float | None] | None = None,
) -> pd.DataFrame:
    """
    Build a minimal DataFrame matching the schema from load_strategy_data().

    Unspecified columns default to NaN.  All lists must have length == n.
    """
    start = date(2020, 1, 2)
    dates = [start + timedelta(days=i) for i in range(n)]

    def _fill(lst, default=np.nan):
        return lst if lst is not None else [default] * n

    return pd.DataFrame(
        {
            "asset_id":     [asset_id] * n,
            "symbol":       [symbol] * n,
            "asset_type":   ["EQUITY"] * n,
            "date":         dates,
            "close":        _fill(close, 100.0),
            "daily_return": _fill(daily_return),
            "sma_20":       _fill(sma_20),
            "sma_50":       _fill(sma_50),
            "sma_200":      _fill(sma_200),
            "ema_20":       _fill(ema_20),
            "ema_50":       _fill(ema_50),
            "ema_200":      [np.nan] * n,
            "volatility_20":  [np.nan] * n,
            "volatility_60":  [np.nan] * n,
            "volatility_252": [np.nan] * n,
        }
    )


# ===========================================================================
# 1. SMA Crossover strategy rules
# ===========================================================================


class TestSMACrossover:
    def test_long_when_fast_above_slow(self):
        """SMA fast > slow -> signal = 1 (LONG)."""
        df = _make_df(sma_20=[110.0, 120.0], sma_50=[100.0, 100.0], n=2)
        result = generate_sma_crossover_signals(df, fast=20, slow=50)
        assert list(result["signal"]) == [1, 1]

    def test_exit_when_fast_below_slow(self):
        """SMA fast < slow -> signal = -1 (EXIT)."""
        df = _make_df(sma_20=[90.0, 80.0], sma_50=[100.0, 100.0], n=2)
        result = generate_sma_crossover_signals(df, fast=20, slow=50)
        assert list(result["signal"]) == [-1, -1]

    def test_flat_when_equal(self):
        """SMA fast == slow -> signal = 0 (FLAT)."""
        df = _make_df(sma_20=[100.0], sma_50=[100.0], n=1)
        result = generate_sma_crossover_signals(df, fast=20, slow=50)
        assert result["signal"].iloc[0] == 0

    def test_crossover_sequence(self):
        """Verify signal flips correctly across a crossover event."""
        # fast rises above slow (crossover)
        sma20 = [90.0, 95.0, 100.0, 105.0, 110.0]
        sma50 = [100.0, 100.0, 100.0, 100.0, 100.0]
        df = _make_df(sma_20=sma20, sma_50=sma50, n=5)
        result = generate_sma_crossover_signals(df, fast=20, slow=50)
        signals = list(result["signal"])
        assert signals == [-1, -1, 0, 1, 1]

    def test_null_when_fast_missing(self):
        """None signal when sma_fast is NaN."""
        df = _make_df(sma_20=[np.nan, 110.0], sma_50=[100.0, 100.0], n=2)
        result = generate_sma_crossover_signals(df, fast=20, slow=50)
        assert result["signal"].iloc[0] is None
        assert result["signal"].iloc[1] == 1

    def test_null_when_slow_missing(self):
        """None signal when sma_slow is NaN."""
        df = _make_df(sma_20=[110.0], sma_50=[np.nan], n=1)
        result = generate_sma_crossover_signals(df, fast=20, slow=50)
        assert result["signal"].iloc[0] is None

    def test_null_when_column_not_precalculated(self):
        """All None when the required SMA window does not exist in df."""
        df = _make_df(n=5)  # no sma_20 or sma_50 values
        # Request a window not in df columns at all
        df = df.drop(columns=["sma_20", "sma_50"], errors="ignore")
        result = generate_sma_crossover_signals(df, fast=20, slow=50)
        assert result["signal"].isna().all()


# ===========================================================================
# 2. EMA Trend strategy rules
# ===========================================================================


class TestEMATrend:
    def test_long_when_fast_above_slow(self):
        """EMA fast > slow -> signal = 1."""
        df = _make_df(ema_20=[115.0], ema_50=[100.0], n=1)
        result = generate_ema_trend_signals(df, fast=20, slow=50)
        assert result["signal"].iloc[0] == 1

    def test_exit_when_fast_below_slow(self):
        """EMA fast < slow -> signal = -1."""
        df = _make_df(ema_20=[85.0], ema_50=[100.0], n=1)
        result = generate_ema_trend_signals(df, fast=20, slow=50)
        assert result["signal"].iloc[0] == -1

    def test_flat_when_equal(self):
        """EMA fast == slow -> signal = 0."""
        df = _make_df(ema_20=[100.0], ema_50=[100.0], n=1)
        result = generate_ema_trend_signals(df, fast=20, slow=50)
        assert result["signal"].iloc[0] == 0

    def test_null_when_indicator_missing(self):
        """None when either EMA is NaN."""
        df = _make_df(ema_20=[np.nan], ema_50=[100.0], n=1)
        result = generate_ema_trend_signals(df, fast=20, slow=50)
        assert result["signal"].iloc[0] is None


# ===========================================================================
# 3. Momentum strategy
# ===========================================================================


class TestMomentum:
    def test_positive_momentum_long(self):
        """momentum > 0 -> signal = 1."""
        # With lookback=1: momentum[1] = close[1]/close[0] - 1 = 110/100-1 = 0.1 > 0
        df = _make_df(close=[100.0, 110.0], n=2)
        result = generate_momentum_signals(df, lookback=1)
        assert result["signal"].iloc[1] == 1

    def test_negative_momentum_exit(self):
        """momentum < 0 -> signal = -1."""
        df = _make_df(close=[110.0, 100.0], n=2)
        result = generate_momentum_signals(df, lookback=1)
        assert result["signal"].iloc[1] == -1

    def test_zero_momentum_flat(self):
        """momentum == 0 -> signal = 0."""
        df = _make_df(close=[100.0, 100.0], n=2)
        result = generate_momentum_signals(df, lookback=1)
        assert result["signal"].iloc[1] == 0

    def test_null_before_lookback_reached(self):
        """First N signals must be None (lookback not yet satisfied)."""
        n = 10
        closes = [float(100 + i) for i in range(n)]
        df = _make_df(close=closes, n=n)
        lookback = 3
        result = generate_momentum_signals(df, lookback=lookback)
        # Rows 0..lookback-1 must be None
        for i in range(lookback):
            assert result["signal"].iloc[i] is None, (
                f"signal at position {i} must be None (lookback not reached)"
            )
        # Row lookback must be non-None
        assert result["signal"].iloc[lookback] is not None

    def test_no_cross_asset_contamination(self):
        """
        Momentum must be computed per asset.
        The first row of asset B must have None signal even if asset A
        has data immediately before it.
        """
        df_a = _make_df(asset_id=_AID_1, close=[100.0, 110.0], n=2)
        # Asset B starts with the same dates — its first row must be None
        df_b = _make_df(asset_id=_AID_2, symbol="BBB", close=[200.0, 220.0], n=2)
        df = pd.concat([df_a, df_b], ignore_index=True).sort_values(
            ["asset_id", "date"]
        ).reset_index(drop=True)

        result = generate_momentum_signals(df, lookback=1)

        # First row of each asset must be None
        for aid in [_AID_1, _AID_2]:
            first_row = result[result["asset_id"] == aid].iloc[0]
            assert first_row["signal"] is None, (
                f"First momentum signal for asset {aid} must be None"
            )


# ===========================================================================
# 4. Mean Reversion strategy
# ===========================================================================


class TestMeanReversion:
    def test_long_when_below_band(self):
        """close < sma*(1-threshold) -> signal = 1."""
        # close=96, sma_20=100, threshold=0.02 → band lower=98 → 96 < 98 → LONG
        df = _make_df(close=[96.0], sma_20=[100.0], n=1)
        result = generate_mean_reversion_signals(df, window=20, threshold=0.02)
        assert result["signal"].iloc[0] == 1

    def test_exit_when_above_band(self):
        """close > sma*(1+threshold) -> signal = -1."""
        # close=104, sma_20=100, threshold=0.02 → band upper=102 → 104 > 102 → EXIT
        df = _make_df(close=[104.0], sma_20=[100.0], n=1)
        result = generate_mean_reversion_signals(df, window=20, threshold=0.02)
        assert result["signal"].iloc[0] == -1

    def test_flat_within_band(self):
        """close within [sma*(1-t), sma*(1+t)] -> signal = 0."""
        # close=100.5, band=[98, 102] → within → FLAT
        df = _make_df(close=[100.5], sma_20=[100.0], n=1)
        result = generate_mean_reversion_signals(df, window=20, threshold=0.02)
        assert result["signal"].iloc[0] == 0

    def test_exact_band_boundary_is_flat(self):
        """Exactly at the band boundary (close == lower_band) is FLAT, not LONG."""
        # close=98, lower_band=98 → close is NOT strictly < lower → FLAT
        df = _make_df(close=[98.0], sma_20=[100.0], n=1)
        result = generate_mean_reversion_signals(df, window=20, threshold=0.02)
        assert result["signal"].iloc[0] == 0

    def test_null_when_sma_missing(self):
        """None when SMA is NaN."""
        df = _make_df(close=[100.0], sma_20=[np.nan], n=1)
        result = generate_mean_reversion_signals(df, window=20, threshold=0.02)
        assert result["signal"].iloc[0] is None

    def test_null_when_close_missing(self):
        """None when close price is NaN."""
        df = _make_df(close=[np.nan], sma_20=[100.0], n=1)
        result = generate_mean_reversion_signals(df, window=20, threshold=0.02)
        assert result["signal"].iloc[0] is None


# ===========================================================================
# 5. Signal values are only -1, 0, 1, or None
# ===========================================================================


class TestSignalValues:
    def _all_signal_values(self, df: pd.DataFrame) -> set:
        """Collect all non-null signal values from every strategy."""
        sigs = pd.concat(
            [
                generate_sma_crossover_signals(df, 20, 50),
                generate_ema_trend_signals(df, 20, 50),
                generate_momentum_signals(df, 3),
                generate_mean_reversion_signals(df, 20, 0.02),
            ]
        )
        return set(sigs["signal"].dropna().unique())

    def test_only_valid_values(self):
        """All non-null signals must be in {-1, 0, 1}."""
        df = _make_df(
            close=[100.0, 105.0, 98.0, 103.0, 97.0, 102.0],
            sma_20=[100.0, 102.0, 101.0, 103.0, 99.0, 101.0],
            sma_50=[100.0, 100.0, 101.0, 101.0, 102.0, 102.0],
            ema_20=[100.0, 102.0, 101.0, 103.0, 99.0, 101.0],
            ema_50=[100.0, 100.0, 101.0, 101.0, 102.0, 102.0],
            n=6,
        )
        values = self._all_signal_values(df)
        assert values.issubset({-1, 0, 1}), (
            f"Unexpected signal values: {values - {-1, 0, 1}}"
        )


# ===========================================================================
# 6. Missing indicators produce None signal
# ===========================================================================


class TestMissingIndicators:
    def test_sma_crossover_all_none_when_all_nan(self):
        """When all SMA values are NaN, every signal must be None."""
        df = _make_df(n=5)  # sma_20, sma_50 all NaN by default
        result = generate_sma_crossover_signals(df, 20, 50)
        assert result["signal"].isna().all()

    def test_ema_trend_all_none_when_all_nan(self):
        df = _make_df(n=5)
        result = generate_ema_trend_signals(df, 20, 50)
        assert result["signal"].isna().all()

    def test_momentum_none_before_lookback(self):
        """With lookback=5 on n=5 rows, signals 0..4 must be None."""
        df = _make_df(close=[float(i + 1) for i in range(5)], n=5)
        result = generate_momentum_signals(df, lookback=5)
        assert result["signal"].isna().all()

    def test_mean_reversion_none_when_sma_all_nan(self):
        df = _make_df(close=[100.0] * 5, n=5)  # sma_20 NaN
        result = generate_mean_reversion_signals(df, window=20, threshold=0.02)
        assert result["signal"].isna().all()

    def test_partial_availability(self):
        """
        Rows with valid indicators get a signal; rows with NaN get None.
        """
        # Row 0: sma_20 = NaN → None
        # Row 1: sma_20 = 110, sma_50 = 100 → LONG (1)
        df = _make_df(
            sma_20=[np.nan, 110.0],
            sma_50=[100.0,  100.0],
            n=2,
        )
        result = generate_sma_crossover_signals(df, 20, 50)
        assert result["signal"].iloc[0] is None
        assert result["signal"].iloc[1] == 1


# ===========================================================================
# 7. No future data (look-ahead bias)
# ===========================================================================


class TestNoLookahead:
    def test_momentum_uses_only_past_closes(self):
        """
        Momentum at position i must equal close[i]/close[i-lookback] - 1.
        This verifies the backward-looking direction of pct_change.
        """
        closes = [100.0, 105.0, 110.0, 104.0, 99.0]
        lookback = 2
        df = _make_df(close=closes, n=len(closes))
        result = generate_momentum_signals(df, lookback=lookback)

        # At position 2: 110/100 - 1 = 0.10 > 0 → LONG
        assert result["signal"].iloc[2] == 1

        # At position 3: 104/105 - 1 ≈ -0.0095 < 0 → EXIT
        assert result["signal"].iloc[3] == -1

        # At position 4: 99/110 - 1 ≈ -0.1 < 0 → EXIT
        assert result["signal"].iloc[4] == -1

    def test_sma_signal_only_uses_current_mas(self):
        """
        The signal at date T is based solely on sma values at T.
        We verify by inverting the future and confirming the signal at T
        is unchanged.
        """
        sma20 = [110.0, 90.0]   # T=0: above, T=1: below
        sma50 = [100.0, 100.0]
        df = _make_df(sma_20=sma20, sma_50=sma50, n=2)
        result = generate_sma_crossover_signals(df, 20, 50)

        # T=0 must be LONG (110>100) regardless of T=1
        assert result["signal"].iloc[0] == 1
        # T=1 must be EXIT (90<100)
        assert result["signal"].iloc[1] == -1


# ===========================================================================
# 8. Parameters stored correctly
# ===========================================================================


class TestParameters:
    def test_sma_parameters_stored(self):
        """generate_sma_crossover_signals stores correct parameters dict."""
        df = _make_df(sma_20=[110.0], sma_50=[100.0], n=1)
        result = generate_sma_crossover_signals(df, fast=20, slow=50)
        assert result["parameters"].iloc[0] == {"fast_window": 20, "slow_window": 50}

    def test_ema_parameters_stored(self):
        df = _make_df(ema_20=[110.0], ema_50=[100.0], n=1)
        result = generate_ema_trend_signals(df, fast=20, slow=50)
        assert result["parameters"].iloc[0] == {"fast_window": 20, "slow_window": 50}

    def test_momentum_parameters_stored(self):
        df = _make_df(close=[100.0, 110.0], n=2)
        result = generate_momentum_signals(df, lookback=20)
        assert result["parameters"].iloc[0] == {"lookback": 20}

    def test_mean_reversion_parameters_stored(self):
        df = _make_df(close=[96.0], sma_20=[100.0], n=1)
        result = generate_mean_reversion_signals(df, window=20, threshold=0.02)
        p = result["parameters"].iloc[0]
        assert p["window"] == 20
        assert abs(p["threshold"] - 0.02) < 1e-9

    def test_strategy_name_stored(self):
        """Every row carries the correct strategy_name."""
        df = _make_df(sma_20=[110.0], sma_50=[100.0], n=1)
        assert generate_sma_crossover_signals(df, 20, 50)["strategy_name"].iloc[0] == "SMA_CROSSOVER"
        assert generate_ema_trend_signals(_make_df(ema_20=[110.0], ema_50=[100.0], n=1), 20, 50)["strategy_name"].iloc[0] == "EMA_TREND"
        assert generate_momentum_signals(_make_df(close=[100.0, 110.0], n=2), 1)["strategy_name"].iloc[0] == "MOMENTUM"
        assert generate_mean_reversion_signals(_make_df(close=[96.0], sma_20=[100.0], n=1), 20, 0.02)["strategy_name"].iloc[0] == "MEAN_REVERSION"


# ===========================================================================
# 9. Different parameter configs treated as different strategies
# ===========================================================================


class TestDifferentConfigs:
    def test_different_params_pass_validation(self):
        """
        Two SMA_CROSSOVER signals with different parameters must NOT be
        treated as duplicates by validate_signals.
        """
        df = _make_df(
            sma_20=[110.0] * 3, sma_50=[100.0] * 3, sma_200=[80.0] * 3, n=3
        )
        sig1 = generate_sma_crossover_signals(df, fast=20, slow=50)
        sig2 = generate_sma_crossover_signals(df, fast=50, slow=200)

        combined = pd.concat([sig1, sig2], ignore_index=True)
        # Should NOT raise
        validate_signals(combined)

    def test_same_params_same_strategy_detected_as_duplicate(self):
        """
        Concatenating the same strategy result twice must raise a
        ValueError due to duplicate detection in validate_signals.
        """
        df = _make_df(sma_20=[110.0], sma_50=[100.0], n=1)
        sig = generate_sma_crossover_signals(df, fast=20, slow=50)
        doubled = pd.concat([sig, sig], ignore_index=True)

        with pytest.raises(ValueError, match="duplicate"):
            validate_signals(doubled)

    def test_different_lookbacks_are_independent(self):
        """Two Momentum configs with different lookbacks must both pass."""
        df = _make_df(close=[float(i + 100) for i in range(25)], n=25)
        sig1 = generate_momentum_signals(df, lookback=5)
        sig2 = generate_momentum_signals(df, lookback=20)

        combined = pd.concat([sig1, sig2], ignore_index=True)
        validate_signals(combined)

    def test_parameters_serialise_consistently(self):
        """
        Parameters dict serialised with sort_keys=True must produce the
        same string regardless of dict insertion order.
        This is critical for the JSONB unique constraint in Supabase.
        """
        p1 = {"fast_window": 20, "slow_window": 50}
        p2 = {"slow_window": 50, "fast_window": 20}
        assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)
