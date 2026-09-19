import pandas as pd
import numpy as np

def calc_sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window).mean()

def calc_ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()

def calc_drawdown(prices: pd.Series):
    cummax = prices.cummax()
    drawdown = (prices - cummax) / cummax
    max_dd = drawdown.min()
    return drawdown, max_dd

def calc_annualized_volatility(returns: pd.Series, N: int) -> float:
    if returns.empty or len(returns) < 2: return 0.0
    return returns.std(ddof=1) * np.sqrt(N)

def calc_sharpe(returns: pd.Series, N: int, rf_annual: float = 0.0) -> float:
    if returns.empty or len(returns) < 2 or returns.std(ddof=1) == 0:
        return 0.0
    rf_period = (1.0 + rf_annual) ** (1.0 / N) - 1.0
    excess = returns - rf_period
    return (excess.mean() / excess.std(ddof=1)) * np.sqrt(N)

def calc_sortino(returns: pd.Series, N: int, rf_annual: float = 0.0) -> float:
    if returns.empty or len(returns) < 2: return 0.0
    rf_period = (1.0 + rf_annual) ** (1.0 / N) - 1.0
    excess = returns - rf_period
    downside = excess[excess < 0]
    if downside.empty or downside.std(ddof=1) == 0:
        return 0.0
    return (excess.mean() / downside.std(ddof=1)) * np.sqrt(N)

def calc_calmar(prices: pd.Series, returns: pd.Series, N: int) -> float:
    if len(prices) < 2: return 0.0
    cagr = (prices.iloc[-1] / prices.iloc[0]) ** (1 / (len(prices) / N)) - 1
    _, max_dd = calc_drawdown(prices)
    if max_dd == 0:
        return 0.0
    return cagr / abs(max_dd)
