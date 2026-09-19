import pandas as pd
import numpy as np

def label_bull_bear(df: pd.DataFrame, window: int = 252) -> pd.Series:
    sma = df['Close'].rolling(window=window).mean()
    regime = pd.Series("Bear", index=df.index)
    regime.loc[df['Close'] > sma] = "Bull"
    regime.loc[sma.isna()] = "Unknown"
    return regime

def label_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    rets = df['Close'].pct_change()
    vol = rets.rolling(window=window).std(ddof=1)
    
    expanding_median = vol.expanding().median()
    
    regime = pd.Series("Low", index=df.index)
    regime.loc[vol > expanding_median] = "High"
    regime.loc[vol.isna()] = "Unknown"
    return regime
