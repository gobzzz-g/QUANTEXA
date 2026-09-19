import pytest
import pandas as pd
import numpy as np
from app.backtest.engine import BacktestEngine
from app.strategies.base import BaseStrategy

class DummyCrossoverStrategy(BaseStrategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        signal = pd.Series(0, index=df.index)
        if len(df) > 1:
            signal.iloc[1] = 1 
        return signal

class AlwaysLongStrategy(BaseStrategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1, index=df.index)
        
class AlwaysNaNStrategy(BaseStrategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(np.nan, index=df.index)

def test_execution_rules():
    dates = pd.date_range("2023-01-01", periods=4, freq="D")
    df = pd.DataFrame({
        "Open": [100, 105, 110, 115],
        "Close": [102, 108, 112, 118]
    }, index=dates)
    
    strat = DummyCrossoverStrategy()
    signal = strat.generate_positions(df)
    
    engine = BacktestEngine(df, signal, ann_factor=252, initial_capital=1000, commission_pct=0.0, slippage_bps=0.0)
    res = engine.run()
    
    trades = res["trades"]
    assert len(trades) > 0
    first_trade = trades[0]
    
    assert first_trade["entry_date"] == dates[2].strftime("%Y-%m-%d")
    assert first_trade["entry_price"] == 110
    
    signal.iloc[-1] = 1 
    engine2 = BacktestEngine(df, signal, ann_factor=252)
    res2 = engine2.run()
    assert len(res2["trades"]) == len(trades)

def test_accounting_identity():
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    df = pd.DataFrame({
        "Open": [100, 105, 110, 115, 120],
        "Close": [102, 108, 112, 118, 122]
    }, index=dates)
    
    strat = AlwaysLongStrategy()
    signal = strat.generate_positions(df)
    
    engine = BacktestEngine(df, signal, ann_factor=252, initial_capital=1000, commission_pct=0.001)
    engine.run()
    
    for i in range(len(engine.dates)):
        cash = engine.cash_curve[i]
        units = engine.position_curve[i]
        price = df["Close"].iloc[i]
        equity = engine.equity_curve[i]
        
        assert pytest.approx(cash + units * price, 0.0001) == equity

def test_benchmark():
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    df = pd.DataFrame({
        "Open": [100, 105, 110, 115, 120],
        "Close": [102, 108, 112, 118, 122]
    }, index=dates)
    
    strat = AlwaysLongStrategy()
    signal = strat.generate_positions(df)
    
    engine = BacktestEngine(df, signal, ann_factor=252, initial_capital=1000, commission_pct=0.0, slippage_bps=0.0)
    res = engine.run()
    
    # Benchmark enters at open of day 1 (100)
    # Day 1 close is 102. Units = 1000/100 = 10. Cash = 0. Equity at close = 10 * 102 = 1020.
    first_b_eq = list(res["benchmark_curve"].values())[0]
    assert first_b_eq == 1020.0


def test_higher_fees_lower_equity():
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    df = pd.DataFrame({
        "Open": [100, 105, 110, 115, 120],
        "Close": [102, 108, 112, 118, 122]
    }, index=dates)
    
    strat = DummyCrossoverStrategy()
    signal = strat.generate_positions(df)
    
    engine1 = BacktestEngine(df, signal, ann_factor=252, initial_capital=1000, commission_pct=0.0)
    res1 = engine1.run()
    
    engine2 = BacktestEngine(df, signal, ann_factor=252, initial_capital=1000, commission_pct=0.01) 
    res2 = engine2.run()
    
    assert res2["strategy"]["cagr"] < res1["strategy"]["cagr"]

def test_warm_up_rules():
    dates = pd.date_range("2023-01-01", periods=3, freq="D")
    df = pd.DataFrame({
        "Open": [100, 105, 110],
        "Close": [102, 108, 112]
    }, index=dates)
    
    strat = AlwaysNaNStrategy()
    signal = strat.generate_positions(df)
    
    engine = BacktestEngine(df, signal, ann_factor=252)
    res = engine.run()
    
    assert len(res["trades"]) == 0
    assert "verdict" in res

def test_no_lookahead_bias():
    dates = pd.date_range("2023-01-01", periods=3, freq="D")
    df = pd.DataFrame({
        "Open": [100, 200, 300],
        "Close": [150, 250, 350]
    }, index=dates)
    
    # A perfect lookahead strategy would buy on day 1 if day 1 close > open. 
    # But we can only generate a signal using data UP TO close of day 1, and execute open of day 2.
    class LookaheadAttemptStrategy(BaseStrategy):
        def generate_positions(self, df: pd.DataFrame) -> pd.Series:
            signal = pd.Series(0, index=df.index)
            # generate signal on day 1
            signal.iloc[0] = 1
            return signal
            
    strat = LookaheadAttemptStrategy()
    signal = strat.generate_positions(df)
    
    engine = BacktestEngine(df, signal, ann_factor=252, initial_capital=1000, commission_pct=0.0, slippage_bps=0.0)
    res = engine.run()
    
    # Check that execution does NOT happen on day 1 (index 0). It MUST happen on day 2 (index 1) open.
    trades = res["trades"]
    assert len(trades) > 0
    assert trades[0]["entry_date"] == dates[1].strftime("%Y-%m-%d")
    assert trades[0]["entry_price"] == df["Open"].iloc[1] # Executed at 200, not 100 or 150.
