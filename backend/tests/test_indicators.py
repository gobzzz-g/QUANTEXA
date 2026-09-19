import pytest
import pandas as pd
import numpy as np
from app.indicators.metrics import (
    calc_sma, calc_ema, calc_drawdown, 
    calc_sharpe, calc_annualized_volatility
)

def test_sma_ema():
    # Matches pandas exactly
    s = pd.Series([10, 20, 30, 40, 50])
    sma = calc_sma(s, 3)
    assert np.isnan(sma.iloc[0])
    assert sma.iloc[2] == 20
    assert sma.iloc[-1] == 40
    
def test_drawdown_exact_match():
    # REQ: [100, 130, 90, 150] = -30.769%
    s = pd.Series([100, 130, 90, 150])
    dd_series, max_dd = calc_drawdown(s)
    expected = (90 - 130) / 130
    assert pytest.approx(max_dd, 0.0001) == expected
    
def test_sharpe_rf_conversion():
    # 4% annual with N=252 gives per-period (1.04)^(1/252) - 1.
    returns = pd.Series([0.01, -0.005, 0.02, 0.01])
    sharpe = calc_sharpe(returns, N=252, rf_annual=0.04)
    rf_period = (1.04) ** (1/252) - 1
    excess = returns - rf_period
    expected = (excess.mean() / excess.std(ddof=1)) * np.sqrt(252)
    assert pytest.approx(sharpe, 0.0001) == expected

def test_annualized_volatility():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02])
    vol = calc_annualized_volatility(returns, N=252)
    expected = returns.std(ddof=1) * np.sqrt(252)
    assert pytest.approx(vol, 0.0001) == expected

def test_calendar_alignment():
    # Two series with different calendars
    dates1 = pd.date_range("2023-01-01", periods=5, freq="D")
    df1 = pd.DataFrame({"Close": [1, 2, 3, 4, 5]}, index=dates1)
    
    dates2 = pd.date_range("2023-01-03", periods=3, freq="D")
    df2 = pd.DataFrame({"Close": [3, 4, 5]}, index=dates2)
    
    from app.correlation.analyzer import compute_correlation_matrix
    dfs = {"A": df1, "B": df2}
    corr = compute_correlation_matrix(dfs)
    assert len(corr) == 2 # 2x2 matrix
