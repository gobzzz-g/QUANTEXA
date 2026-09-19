import pandas as pd
import logging

logger = logging.getLogger(__name__)

def clean_ohlcv(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    # Coerce index to datetime and drop NaNs
    df.index = pd.to_datetime(df.index, errors='coerce')
    df = df[~df.index.isna()]
    
    # Sort
    df = df.sort_index()
    
    # Dedupe by index
    dupes = df.index.duplicated()
    if dupes.any():
        logger.warning(f"[{ticker}] Dropped {dupes.sum()} duplicate rows.")
        df = df[~dupes]
        
    # Coerce to numeric to prevent TypeError on strings
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    # Drop non-positive prices for OHLC
    for col in ['Open', 'High', 'Low', 'Close']:
        if col in df.columns:
            invalid = df[col] <= 0
            if invalid.any():
                logger.warning(f"[{ticker}] Dropped {invalid.sum()} rows with non-positive {col}.")
                df = df[~invalid]
                
    # Forward-fill NaNs up to 3 days
    nans_before = df['Close'].isna().sum()
    df = df.ffill(limit=3)
    nans_after = df['Close'].isna().sum()
    if nans_before > nans_after:
        logger.warning(f"[{ticker}] Forward-filled {nans_before - nans_after} NaNs (limit 3).")
        
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
    return df
