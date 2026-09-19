import pandas as pd
import numpy as np
from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    @abstractmethod
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        pass

class SMACrossover(BaseStrategy):
    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow
        
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        from ..indicators.metrics import calc_sma
        fast_sma = calc_sma(df['Close'], self.fast)
        slow_sma = calc_sma(df['Close'], self.slow)
        
        signal = (fast_sma > slow_sma).astype(int)
        signal.loc[slow_sma.isna()] = np.nan
        return signal

class EMATrend(BaseStrategy):
    def __init__(self, fast: int = 12, slow: int = 26):
        self.fast = fast
        self.slow = slow
        
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        from ..indicators.metrics import calc_ema
        fast_ema = calc_ema(df['Close'], self.fast)
        slow_ema = calc_ema(df['Close'], self.slow)
        
        signal = (fast_ema > slow_ema).astype(int)
        return signal

class Momentum(BaseStrategy):
    def __init__(self, lookback: int = 90, threshold: float = 0.0):
        self.lookback = lookback
        self.threshold = threshold
        
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        returns = df['Close'].pct_change(periods=self.lookback)
        signal = (returns > self.threshold).astype(int)
        signal.loc[returns.isna()] = np.nan
        return signal

class MeanReversion(BaseStrategy):
    def __init__(self, lookback: int = 20, z_enter: float = -2.0, z_exit: float = 0.0):
        self.lookback = lookback
        self.z_enter = z_enter
        self.z_exit = z_exit
        
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        mean = df['Close'].rolling(window=self.lookback).mean()
        std = df['Close'].rolling(window=self.lookback).std(ddof=1)
        
        z = (df['Close'] - mean) / std
        
        signal = pd.Series(np.nan, index=df.index, dtype=float)
        position = 0
        
        for i in range(len(df)):
            z_val = z.iloc[i]
            if pd.isna(z_val):
                continue
                
            if position == 0 and z_val < self.z_enter:
                position = 1
            elif position == 1 and z_val >= self.z_exit:
                position = 0
                
            signal.iloc[i] = position
            
        return signal
