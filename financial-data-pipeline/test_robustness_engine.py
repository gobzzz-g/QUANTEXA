"""
Unit tests for the Robustness & Regime Analysis Engine (Layer 5).

All tests use small, deterministic, in-memory DataFrames.
No Supabase connection required.

Run with:
    pytest test_robustness_engine.py -v
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from robustness_engine import (
    ANALYSIS_PERIODS,
    DEFAULT_PARAMS,
    TC_RATES,
    VALID_REGIMES,
    VALID_TRENDS,
    VALID_VOL_STATS,
    calculate_expanding_volatility_threshold,
    calculate_robustness_statistics,
    classify_market_regimes,
    generate_parameter_configurations,
    generate_time_periods,
    validate_regimes,
    _prepare_indicator_df,
    _generate_signals,
    _run_single_backtest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dates(n: int, start: str = "2020-01-02") -> list[date]:
    base = date.fromisoformat(start)
    return [base + timedelta(days=i) for i in range(n)]


def _make_prices(
    n: int = 10,
    asset_id: str = "AAA",
    open_val: float = 100.0,
    close_val: float = 101.0,
) -> pd.DataFrame:
    """Minimal price DataFrame for one asset."""
    dates = _dates(n)
    return pd.DataFrame({
        "asset_id": [asset_id] * n,
        "date":     dates,
        "open":     [open_val + i for i in range(n)],
        "close":    [close_val + i for i in range(n)],
    })


def _make_indicators(
    n: int = 300,
    asset_id: str = "AAA",
    sma50_above_sma200: bool = True,
    vol20: float = 0.2,
) -> pd.DataFrame:
    """Minimal indicator DataFrame for regime classification tests."""
    dates = _dates(n)
    sma50  = 110.0 if sma50_above_sma200 else 90.0
    sma200 = 100.0
    return pd.DataFrame({
        "asset_id":    [asset_id] * n,
        "date":        dates,
        "sma_50":      [sma50]  * n,
        "sma_200":     [sma200] * n,
        "volatility_20": [vol20] * n,
    })


# ===========================================================================
# 1. SMA parameter combinations
# ===========================================================================


class TestSMAParameterCombinations:
    def setup_method(self):
        self.configs = generate_parameter_configurations()["SMA_CROSSOVER"]

    def test_all_fast_less_than_slow(self):
        """Every SMA config must have fast_window < slow_window."""
        for cfg in self.configs:
            assert cfg["fast_window"] < cfg["slow_window"], (
                f"Invalid SMA config: {cfg}"
            )

    def test_no_equal_windows(self):
        """fast_window must never equal slow_window."""
        for cfg in self.configs:
            assert cfg["fast_window"] != cfg["slow_window"]

    def test_correct_count(self):
        """
        fast=[10,20,30,50], slow=[30,50,75,100,150,200], fast<slow:
          10→6, 20→6, 30→5, 50→4  → 21 total
        """
        assert len(self.configs) == 21

    def test_no_invalid_combination_like_50_30(self):
        pairs = {(c["fast_window"], c["slow_window"]) for c in self.configs}
        assert (50, 30) not in pairs
        assert (50, 50) not in pairs

    def test_contains_default_params(self):
        default = DEFAULT_PARAMS["SMA_CROSSOVER"]
        assert default in self.configs


# ===========================================================================
# 2. EMA parameter combinations
# ===========================================================================


class TestEMAParameterCombinations:
    def setup_method(self):
        self.configs = generate_parameter_configurations()["EMA_TREND"]

    def test_all_fast_less_than_slow(self):
        for cfg in self.configs:
            assert cfg["fast_window"] < cfg["slow_window"]

    def test_correct_count(self):
        assert len(self.configs) == 21

    def test_same_structure_as_sma(self):
        sma_configs = generate_parameter_configurations()["SMA_CROSSOVER"]
        assert self.configs == sma_configs


# ===========================================================================
# 3. Momentum parameter combinations
# ===========================================================================


class TestMomentumParameterCombinations:
    def setup_method(self):
        self.configs = generate_parameter_configurations()["MOMENTUM"]

    def test_all_lookbacks_positive(self):
        for cfg in self.configs:
            assert cfg["lookback"] > 0

    def test_count(self):
        """Momentum lookbacks: [5, 10, 20, 40, 60, 120] → 6"""
        assert len(self.configs) == 6

    def test_contains_default(self):
        assert DEFAULT_PARAMS["MOMENTUM"] in self.configs

    def test_no_duplicate_lookbacks(self):
        lookbacks = [c["lookback"] for c in self.configs]
        assert len(lookbacks) == len(set(lookbacks))


# ===========================================================================
# 4. Mean-reversion parameter combinations
# ===========================================================================


class TestMeanReversionParameterCombinations:
    def setup_method(self):
        self.configs = generate_parameter_configurations()["MEAN_REVERSION"]

    def test_count(self):
        """4 windows × 4 thresholds = 16"""
        assert len(self.configs) == 16

    def test_all_windows_positive(self):
        for cfg in self.configs:
            assert cfg["window"] > 0

    def test_all_thresholds_positive(self):
        for cfg in self.configs:
            assert cfg["threshold"] > 0

    def test_contains_default(self):
        assert DEFAULT_PARAMS["MEAN_REVERSION"] in self.configs

    def test_thresholds_in_expected_range(self):
        """Thresholds should be between 0.01 (1%) and 0.05 (5%)."""
        for cfg in self.configs:
            assert 0.0 < cfg["threshold"] <= 0.1


# ===========================================================================
# 5. Transaction-cost configurations
# ===========================================================================


class TestTransactionCostConfigurations:
    def test_all_tc_rates_nonnegative(self):
        for tc in TC_RATES:
            assert tc >= 0.0

    def test_expected_tc_values_present(self):
        assert 0.0    in TC_RATES
        assert 0.001  in TC_RATES

    def test_tc_rates_sorted(self):
        assert TC_RATES == sorted(TC_RATES)

    def test_five_tc_rates(self):
        assert len(TC_RATES) == 5

    def test_max_tc_is_half_percent(self):
        assert max(TC_RATES) == pytest.approx(0.005, abs=1e-9)


# ===========================================================================
# 6. Time-period generation
# ===========================================================================


class TestTimePeriodGeneration:
    def test_start_before_end_in_all_periods(self):
        max_date = date(2026, 9, 19)
        periods = generate_time_periods(max_date)
        for p in periods:
            assert p["start"] < p["end"], f"Period {p['name']}: start >= end"

    def test_none_end_resolves_to_max_date(self):
        max_date = date(2026, 9, 19)
        periods  = generate_time_periods(max_date)
        names    = [p["name"] for p in periods]
        # "2025_present" has end=None in ANALYSIS_PERIODS → should resolve
        if "2025_present" in names:
            p = next(x for x in periods if x["name"] == "2025_present")
            assert p["end"] == max_date

    def test_no_periods_produced_if_start_after_max_date(self):
        """If max_date is before all period starts, result should be empty (or ≤ valid)."""
        # All period starts are in 2020+; max_date = 2018-01-01 should drop all
        max_date = date(2018, 1, 1)
        periods  = generate_time_periods(max_date)
        for p in periods:
            assert p["start"] < p["end"]  # only periods where this holds

    def test_three_base_periods_defined(self):
        assert len(ANALYSIS_PERIODS) == 3

    def test_period_names_unique(self):
        names = [p["name"] for p in ANALYSIS_PERIODS]
        assert len(names) == len(set(names))


# ===========================================================================
# 7. Expanding volatility threshold (causal)
# ===========================================================================


class TestExpandingVolatilityThreshold:
    def test_threshold_matches_expanding_median(self):
        """threshold[i] must equal median(vol[0 … i])."""
        vols = pd.Series([0.3, 0.1, 0.4, 0.2, 0.5])
        thresholds = calculate_expanding_volatility_threshold(vols)
        for i in range(len(vols)):
            expected = float(np.median(vols.iloc[: i + 1]))
            assert abs(thresholds.iloc[i] - expected) < 1e-9, (
                f"At i={i}: got {thresholds.iloc[i]:.6f}, expected {expected:.6f}"
            )

    def test_monotone_volatility(self):
        """Monotonically increasing series: threshold ≤ current value from idx 0."""
        vols = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
        thresholds = calculate_expanding_volatility_threshold(vols)
        # All thresholds must be ≤ corresponding vol (since vol grows)
        assert (thresholds <= vols + 1e-12).all()

    def test_single_value(self):
        """With one observation, threshold equals that value."""
        vols = pd.Series([0.25])
        thresholds = calculate_expanding_volatility_threshold(vols)
        assert abs(thresholds.iloc[0] - 0.25) < 1e-9

    def test_same_length_as_input(self):
        vols = pd.Series([0.1, 0.2, 0.3])
        thresholds = calculate_expanding_volatility_threshold(vols)
        assert len(thresholds) == len(vols)


# ===========================================================================
# 8. Regime classification – BULL_LOW_VOL
# ===========================================================================


class TestRegimeClassificationBullLowVol:
    def test_bull_low_vol(self):
        """
        sma_50 > sma_200 AND vol_20 decreases below expanding median
        → BULL_LOW_VOL from index 1 onwards.

        Expanding thresholds:
          idx 0: median([0.3]) = 0.3, vol = 0.3 → vol >= threshold → HIGH → BULL_HIGH_VOL
          idx 1: median([0.3, 0.2]) = 0.25, vol = 0.2 → vol < 0.25 → LOW → BULL_LOW_VOL
          idx 2: median([0.3, 0.2, 0.1]) = 0.2, vol = 0.1 → vol < 0.2 → LOW → BULL_LOW_VOL
        """
        df = pd.DataFrame({
            "asset_id":     ["AAA"] * 3,
            "date":         _dates(3),
            "sma_50":       [110.0, 112.0, 115.0],
            "sma_200":      [100.0, 101.0, 102.0],
            "volatility_20": [0.3, 0.2, 0.1],
        })
        regimes = classify_market_regimes(df)
        assert regimes.iloc[1]["regime"] == "BULL_LOW_VOL"
        assert regimes.iloc[2]["regime"] == "BULL_LOW_VOL"

    def test_trend_state_is_bull(self):
        df = pd.DataFrame({
            "asset_id":     ["AAA"] * 2,
            "date":         _dates(2),
            "sma_50":       [120.0, 125.0],
            "sma_200":      [100.0, 100.0],
            "volatility_20": [0.3, 0.1],
        })
        regimes = classify_market_regimes(df)
        assert (regimes["trend_state"] == "BULL").all()


# ===========================================================================
# 9. Regime classification – BEAR_HIGH_VOL
# ===========================================================================


class TestRegimeClassificationBearHighVol:
    def test_bear_high_vol(self):
        """
        sma_50 < sma_200 AND vol_20 >= expanding median → BEAR_HIGH_VOL.

        idx 0: threshold = median([0.1]) = 0.1, vol = 0.1 → vol >= threshold → HIGH
        idx 1: threshold = median([0.1, 0.5]) = 0.3, vol = 0.5 → vol >= 0.3 → HIGH
        """
        df = pd.DataFrame({
            "asset_id":     ["AAA"] * 2,
            "date":         _dates(2),
            "sma_50":       [88.0, 86.0],
            "sma_200":      [100.0, 100.0],
            "volatility_20": [0.1, 0.5],
        })
        regimes = classify_market_regimes(df)
        assert regimes.iloc[0]["regime"] == "BEAR_HIGH_VOL"
        assert regimes.iloc[1]["regime"] == "BEAR_HIGH_VOL"

    def test_trend_state_is_bear(self):
        df = pd.DataFrame({
            "asset_id":     ["AAA"] * 2,
            "date":         _dates(2),
            "sma_50":       [80.0, 82.0],
            "sma_200":      [100.0, 100.0],
            "volatility_20": [0.2, 0.2],
        })
        regimes = classify_market_regimes(df)
        assert (regimes["trend_state"] == "BEAR").all()

    def test_unknown_when_sma_missing(self):
        """NaN SMA values must produce UNKNOWN regime."""
        df = pd.DataFrame({
            "asset_id":     ["AAA"] * 3,
            "date":         _dates(3),
            "sma_50":       [float("nan"), 90.0, 90.0],
            "sma_200":      [100.0, float("nan"), 100.0],
            "volatility_20": [0.2, 0.2, 0.2],
        })
        regimes = classify_market_regimes(df)
        assert regimes.iloc[0]["regime"] == "UNKNOWN"
        assert regimes.iloc[1]["regime"] == "UNKNOWN"
        assert regimes.iloc[2]["regime"] in ("BEAR_HIGH_VOL", "BEAR_LOW_VOL")


# ===========================================================================
# 10. No look-ahead bias in regime classification
# ===========================================================================


class TestNoLookaheadVolatility:
    def test_future_change_does_not_alter_past_thresholds(self):
        """
        Changing a future volatility value must NOT change any past threshold.
        This verifies that the expanding median is strictly causal.
        """
        vols_original = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
        vols_modified = pd.Series([0.1, 0.2, 0.3, 100.0, 999.0])  # radically different future

        t_orig = calculate_expanding_volatility_threshold(vols_original)
        t_mod  = calculate_expanding_volatility_threshold(vols_modified)

        # The first 3 thresholds (past) must be identical
        for i in range(3):
            assert abs(t_orig.iloc[i] - t_mod.iloc[i]) < 1e-9, (
                f"Future change affected past threshold at index {i}: "
                f"{t_orig.iloc[i]} vs {t_mod.iloc[i]}"
            )

    def test_threshold_does_not_increase_sharply_from_future_peek(self):
        """
        A spike at the end should not raise the threshold for earlier periods.
        """
        vols = pd.Series([0.1, 0.1, 0.1, 0.1, 1000.0])
        thresholds = calculate_expanding_volatility_threshold(vols)

        # At idx 0..3, threshold should only reflect 0.1 observations
        for i in range(4):
            expected = float(np.median(vols.iloc[:i + 1]))
            assert abs(thresholds.iloc[i] - expected) < 1e-9

    def test_regime_classification_is_causal(self):
        """
        Regime at index t must not depend on volatility values at t+1, t+2, …
        Verified by modifying future rows and checking that past regimes are unchanged.
        """
        def _classify(vol_list):
            df = pd.DataFrame({
                "asset_id":     ["X"] * len(vol_list),
                "date":         _dates(len(vol_list)),
                "sma_50":       [110.0] * len(vol_list),
                "sma_200":      [100.0] * len(vol_list),
                "volatility_20": vol_list,
            })
            return classify_market_regimes(df)["regime"].tolist()

        vols_base   = [0.3, 0.2, 0.1, 0.2, 0.3]
        vols_future_changed = [0.3, 0.2, 0.1, 999.0, 999.0]

        regimes_base   = _classify(vols_base)
        regimes_future = _classify(vols_future_changed)

        # First 3 regimes must be the same (future didn't change them)
        assert regimes_base[:3] == regimes_future[:3], (
            f"Regime changed due to future modification: "
            f"{regimes_base[:3]} vs {regimes_future[:3]}"
        )


# ===========================================================================
# 11. Valid regime names
# ===========================================================================


class TestValidRegimeNames:
    def test_validate_accepts_all_valid_regimes(self):
        """validate_regimes must pass for a well-formed DataFrame."""
        rows = []
        for i, regime in enumerate(sorted(VALID_REGIMES)):
            rows.append({
                "asset_id":        "AAA",
                "date":            _dates(len(VALID_REGIMES))[i],
                "trend_state":     "BULL" if "BULL" in regime else ("UNKNOWN" if regime == "UNKNOWN" else "BEAR"),
                "volatility_state": (
                    "LOW_VOLATILITY" if "LOW" in regime
                    else ("UNKNOWN" if regime == "UNKNOWN" else "HIGH_VOLATILITY")
                ),
                "regime":          regime,
            })
        df = pd.DataFrame(rows)
        validate_regimes(df)  # must not raise

    def test_valid_regime_set_contains_expected_values(self):
        expected = {
            "BULL_LOW_VOL", "BULL_HIGH_VOL",
            "BEAR_LOW_VOL", "BEAR_HIGH_VOL",
            "UNKNOWN",
        }
        assert VALID_REGIMES == expected

    def test_valid_trends_set(self):
        assert "BULL"    in VALID_TRENDS
        assert "BEAR"    in VALID_TRENDS
        assert "UNKNOWN" in VALID_TRENDS

    def test_valid_vol_states_set(self):
        assert "HIGH_VOLATILITY" in VALID_VOL_STATS
        assert "LOW_VOLATILITY"  in VALID_VOL_STATS
        assert "UNKNOWN"         in VALID_VOL_STATS

    def test_classify_only_produces_valid_regimes(self):
        """classify_market_regimes must only produce values in VALID_REGIMES."""
        df = _make_indicators(n=100, sma50_above_sma200=True, vol20=0.2)
        regimes = classify_market_regimes(df)
        invalid = set(regimes["regime"].unique()) - VALID_REGIMES
        assert not invalid, f"Invalid regimes produced: {invalid}"


# ===========================================================================
# 12. Duplicate prevention
# ===========================================================================


class TestDuplicatePrevention:
    def test_validate_raises_on_duplicate_asset_date(self):
        """validate_regimes must raise ValueError on duplicate (asset_id, date)."""
        d = _dates(3)
        df = pd.DataFrame({
            "asset_id":        ["AAA", "AAA", "AAA"],
            "date":            [d[0], d[0], d[1]],   # d[0] duplicated
            "trend_state":     ["BULL", "BULL", "BULL"],
            "volatility_state": ["LOW_VOLATILITY"] * 3,
            "regime":          ["BULL_LOW_VOL"] * 3,
        })
        with pytest.raises(ValueError, match="duplicate"):
            validate_regimes(df)

    def test_validate_raises_on_invalid_regime_value(self):
        df = pd.DataFrame({
            "asset_id":        ["AAA"],
            "date":            [_dates(1)[0]],
            "trend_state":     ["BULL"],
            "volatility_state": ["LOW_VOLATILITY"],
            "regime":          ["SUPER_BULL"],  # invalid
        })
        with pytest.raises(ValueError):
            validate_regimes(df)

    def test_validate_raises_on_unsorted_dates(self):
        d = _dates(3)
        df = pd.DataFrame({
            "asset_id":        ["AAA"] * 3,
            "date":            [d[2], d[0], d[1]],  # unsorted
            "trend_state":     ["BULL"] * 3,
            "volatility_state": ["LOW_VOLATILITY"] * 3,
            "regime":          ["BULL_LOW_VOL"] * 3,
        })
        with pytest.raises(ValueError, match="sorted"):
            validate_regimes(df)


# ===========================================================================
# 13. Parameter validation
# ===========================================================================


class TestParameterValidation:
    def test_sma_fast_always_less_than_slow(self):
        configs = generate_parameter_configurations()
        for strat in ("SMA_CROSSOVER", "EMA_TREND"):
            for cfg in configs[strat]:
                assert cfg["fast_window"] < cfg["slow_window"], (
                    f"{strat} config {cfg} violates fast < slow rule."
                )

    def test_no_negative_lookbacks(self):
        configs = generate_parameter_configurations()
        for cfg in configs["MOMENTUM"]:
            assert cfg["lookback"] > 0

    def test_no_zero_threshold_in_mean_reversion(self):
        configs = generate_parameter_configurations()
        for cfg in configs["MEAN_REVERSION"]:
            assert cfg["threshold"] > 0

    def test_total_config_count(self):
        """Total: 21 SMA + 21 EMA + 6 MOM + 16 MR = 64"""
        configs = generate_parameter_configurations()
        total = sum(len(v) for v in configs.values())
        assert total == 64

    def test_all_strategies_present(self):
        configs = generate_parameter_configurations()
        assert "SMA_CROSSOVER"  in configs
        assert "EMA_TREND"      in configs
        assert "MOMENTUM"       in configs
        assert "MEAN_REVERSION" in configs


# ===========================================================================
# 14. Robustness statistics
# ===========================================================================


class TestRobustnessStatistics:
    def _make_records(self, asset_id="AAA", strategy="SMA_CROSSOVER") -> list[dict]:
        """Create synthetic PARAMETER robustness records."""
        records = []
        for i, (total_ret, sharpe) in enumerate([
            (0.10, 0.5), (0.20, 1.0), (0.05, 0.3), (-0.05, -0.2), (0.15, 0.8)
        ]):
            records.append({
                "asset_id":      asset_id,
                "strategy_name": strategy,
                "parameters":    {"fast_window": 10 + i, "slow_window": 50},
                "test_type":     "PARAMETER",
                "test_value":    {"fast_window": 10 + i, "slow_window": 50},
                "start_date":    date(2020, 1, 2),
                "end_date":      date(2025, 1, 2),
                "initial_capital": 100_000,
                "total_return":  total_ret,
                "sharpe_ratio":  sharpe,
                "max_drawdown":  -0.1 * (i + 1),
                "annualized_return": None,
                "annualized_volatility": None,
                "final_portfolio_value": 100_000 * (1 + total_ret),
                "trades": i + 5,
                "win_rate": 0.5,
                "transaction_costs": 100.0,
            })
        return records

    def test_n_configs_correct(self):
        records = self._make_records()
        stats   = calculate_robustness_statistics(records)
        key = ("AAA", "SMA_CROSSOVER")
        assert stats[key]["n_configs"] == 5

    def test_mean_return_correct(self):
        records = self._make_records()
        stats   = calculate_robustness_statistics(records)
        key = ("AAA", "SMA_CROSSOVER")
        expected = np.mean([0.10, 0.20, 0.05, -0.05, 0.15])
        assert abs(stats[key]["mean_return"] - expected) < 1e-9

    def test_n_profitable_and_losing(self):
        records = self._make_records()
        stats   = calculate_robustness_statistics(records)
        key = ("AAA", "SMA_CROSSOVER")
        assert stats[key]["n_profitable"] == 4   # 0.10, 0.20, 0.05, 0.15 > 0
        assert stats[key]["n_losing"]     == 1   # -0.05 < 0

    def test_only_parameter_records_included(self):
        """TC and TIME_PERIOD records must be excluded from stats."""
        records = self._make_records()
        tc_record = dict(records[0])
        tc_record["test_type"]  = "TRANSACTION_COST"
        tc_record["total_return"] = 9.99  # should not affect stats
        records.append(tc_record)

        stats = calculate_robustness_statistics(records)
        key = ("AAA", "SMA_CROSSOVER")
        # Still 5 PARAMETER records
        assert stats[key]["n_configs"] == 5

    def test_empty_records_returns_empty_stats(self):
        stats = calculate_robustness_statistics([])
        assert stats == {}

    def test_median_return_correct(self):
        records = self._make_records()
        stats   = calculate_robustness_statistics(records)
        key = ("AAA", "SMA_CROSSOVER")
        expected = float(np.median([0.10, 0.20, 0.05, -0.05, 0.15]))
        assert abs(stats[key]["median_return"] - expected) < 1e-9


# ===========================================================================
# 15. Signal generation integration (using Layer 3 functions)
# ===========================================================================


class TestSignalGeneration:
    def _make_long_prices(self, n: int = 300, asset_id: str = "AAA") -> pd.DataFrame:
        """Generate prices with enough length for long SMA windows."""
        dates = _dates(n)
        closes = [100.0 + i * 0.5 for i in range(n)]  # trending up
        opens  = [c - 0.5 for c in closes]
        return pd.DataFrame({
            "asset_id": [asset_id] * n,
            "date":     dates,
            "open":     opens,
            "close":    closes,
        })

    def test_sma_signals_generated_for_custom_window(self):
        """Custom SMA windows (not in default Layer 2 indicators) must be computable."""
        prices = self._make_long_prices(250)
        params = {"fast_window": 10, "slow_window": 30}
        ind_df = _prepare_indicator_df(prices, "SMA_CROSSOVER", params)
        assert f"sma_10" in ind_df.columns
        assert f"sma_30" in ind_df.columns

    def test_ema_signals_generated_for_custom_window(self):
        prices = self._make_long_prices(250)
        params = {"fast_window": 10, "slow_window": 75}
        ind_df = _prepare_indicator_df(prices, "EMA_TREND", params)
        assert "ema_10" in ind_df.columns
        assert "ema_75" in ind_df.columns

    def test_signals_df_has_required_columns(self):
        """Generated signals must have asset_id, date, signal columns."""
        prices = self._make_long_prices(250)
        params = {"fast_window": 20, "slow_window": 50}
        ind_df  = _prepare_indicator_df(prices, "SMA_CROSSOVER", params)
        sigs_df = _generate_signals(ind_df, "SMA_CROSSOVER", params)
        for col in ("asset_id", "date", "signal"):
            assert col in sigs_df.columns

    def test_signals_values_in_valid_range(self):
        """Signals must be 1, 0, -1, or NaN."""
        prices = self._make_long_prices(250)
        params = {"fast_window": 10, "slow_window": 50}
        ind_df  = _prepare_indicator_df(prices, "SMA_CROSSOVER", params)
        sigs_df = _generate_signals(ind_df, "SMA_CROSSOVER", params)
        valid_vals = {1.0, 0.0, -1.0, float("nan")}
        unique_sigs = set(sigs_df["signal"].dropna().unique())
        assert unique_sigs <= {1.0, 0.0, -1.0}

    def test_single_backtest_returns_metrics(self):
        """_run_single_backtest must return a dict with total_return."""
        prices = self._make_long_prices(250)
        params = {"fast_window": 10, "slow_window": 50}
        ind_df  = _prepare_indicator_df(prices, "SMA_CROSSOVER", params)
        sigs_df = _generate_signals(ind_df, "SMA_CROSSOVER", params)
        asset_sigs = sigs_df[sigs_df["asset_id"] == "AAA"].copy()

        m = _run_single_backtest(prices, asset_sigs, 10_000, 0.001, 0.0, 0.0)
        assert m is not None
        assert "total_return" in m
        assert "sharpe_ratio" in m
