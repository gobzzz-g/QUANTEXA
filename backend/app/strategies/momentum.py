import pandas as pd
from .base import BaseStrategy, register_strategy

@register_strategy("momentum")
class Momentum(BaseStrategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        lookback = self.params.get("lookback", 90)
        threshold = self.params.get("threshold", 0.0)
        
        close = df['Close']
        returns = close.pct_change(periods=lookback)
        
        positions = (returns > threshold).astype(int)
        positions.iloc[:lookback] = 0
        return positions
