import pandas as pd
from .base import BaseStrategy, register_strategy
from ..indicators.metrics import compute_sma, compute_ema

@register_strategy("sma_crossover")
class SMACrossover(BaseStrategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        fast_window = self.params.get("fast", 20)
        slow_window = self.params.get("slow", 50)
        
        close = df['Close']
        fast_sma = compute_sma(close, fast_window)
        slow_sma = compute_sma(close, slow_window)
        
        positions = (fast_sma > slow_sma).astype(int)
        positions.iloc[:slow_window] = 0
        return positions

@register_strategy("ema_trend")
class EMATrend(BaseStrategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        fast_window = self.params.get("fast", 12)
        slow_window = self.params.get("slow", 26)
        trend_filter = self.params.get("trend_filter", 200) # 0 means off
        
        close = df['Close']
        fast_ema = compute_ema(close, fast_window)
        slow_ema = compute_ema(close, slow_window)
        
        signal = fast_ema > slow_ema
        warmup = max(fast_window, slow_window)
        
        if trend_filter > 0:
            trend_sma = compute_sma(close, trend_filter)
            signal = signal & (close > trend_sma)
            warmup = max(warmup, trend_filter)
            
        positions = signal.astype(int)
        positions.iloc[:warmup] = 0
        return positions
