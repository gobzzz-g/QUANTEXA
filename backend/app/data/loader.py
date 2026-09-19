import pandas as pd
import yfinance as yf
import os
import datetime
from .cleaning import clean_ohlcv
from ..config import settings
import logging

logger = logging.getLogger(__name__)

class DataResult:
    def __init__(self, df: pd.DataFrame, source: str, fetched_at: str):
        self.df = df
        self.source = source
        self.fetched_at = fetched_at

def load_data(ticker: str) -> DataResult:
    # 1. Try Supabase
    try:
        from .supabase_client import get_asset_prices
        df = get_asset_prices(ticker)
        if not df.empty:
            df = clean_ohlcv(df, ticker)
            fetched_at = datetime.datetime.utcnow().isoformat()
            return DataResult(df, "supabase", fetched_at)
    except Exception as e:
        logger.warning(f"[{ticker}] Supabase fetch failed: {e}")

    # 2. Try Live (yfinance)
    try:
        df = yf.download(ticker, progress=False)
        if not df.empty:
            df = clean_ohlcv(df, ticker)
            fetched_at = datetime.datetime.utcnow().isoformat()
            _save_to_cache(df, ticker)
            return DataResult(df, "live", fetched_at)
    except Exception as e:
        logger.warning(f"[{ticker}] Live fetch failed: {e}")

    # 3. Try Cache (Parquet)
    cache_path = os.path.join(settings.cache_dir, f"{ticker}.parquet")
    if os.path.exists(cache_path):
        df = pd.read_parquet(cache_path)
        fetched_at = datetime.datetime.fromtimestamp(os.path.getmtime(cache_path)).isoformat()
        return DataResult(df, "cache", fetched_at)
        
    # 4. Try Seed (CSV)
    seed_path = os.path.join(settings.seed_dir, f"{ticker}.csv")
    if os.path.exists(seed_path):
        df = pd.read_csv(seed_path, index_col=0, parse_dates=True)
        df = clean_ohlcv(df, ticker)
        fetched_at = "seed_snapshot"
        return DataResult(df, "seed", fetched_at)
        
    raise ValueError(f"No data available for {ticker} from any source.")

def _save_to_cache(df: pd.DataFrame, ticker: str):
    os.makedirs(settings.cache_dir, exist_ok=True)
    df.to_parquet(os.path.join(settings.cache_dir, f"{ticker}.parquet"))

from typing import List, Dict

def load_overview_data(tickers: List[str]) -> Dict[str, DataResult]:
    from .supabase_client import get_multiple_asset_prices
    
    results = {}
    try:
        dfs = get_multiple_asset_prices(tickers)
        fetched_at = datetime.datetime.utcnow().isoformat()
        
        for ticker, df in dfs.items():
            if not df.empty:
                df = clean_ohlcv(df, ticker)
                results[ticker] = DataResult(df, "supabase", fetched_at)
    except Exception as e:
        logger.warning(f"Supabase batch fetch failed: {e}")
        
    # For any missing, fallback to load_data
    for ticker in tickers:
        if ticker not in results:
            try:
                results[ticker] = load_data(ticker)
            except Exception as e:
                logger.warning(f"Fallback fetch failed for {ticker}: {e}")
                
    return results
