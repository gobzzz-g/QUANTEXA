import pandas as pd
from .base import BaseStrategy, register_strategy
from ..indicators.metrics import compute_sma

@register_strategy("mean_reversion")
class MeanReversion(BaseStrategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        window = self.params.get("lookback", 20)
        z_enter = self.params.get("z_enter", -2.0)
        z_exit = self.params.get("z_exit", 0.0)
        
        close = df['Close']
        sma = compute_sma(close, window)
        std = close.rolling(window=window).std()
        
        # Prevent division by zero
        std = std.replace(0, float('nan'))
        z_score = (close - sma) / std
        
        enter = z_score < z_enter
        exit = z_score >= z_exit
        
        signal = pd.Series(float('nan'), index=df.index)
        signal.loc[enter] = 1
        signal.loc[exit] = 0
        
        signal = signal.ffill().fillna(0)
        positions = signal.astype(int)
        positions.iloc[:window] = 0
        
        return positions
