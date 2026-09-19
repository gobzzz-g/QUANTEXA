import pytest
import pandas as pd
import numpy as np
import os
from app.data.cleaning import clean_ohlcv
from app.data.loader import load_data
from app.config import settings

def test_registry():
    assert "BTC-USD" in settings.assets
    assert "GC=F" in settings.assets
    assert settings.assets["BTC-USD"].calendar_days == 365
    assert settings.assets["GC=F"].calendar_days == 252

def test_cleaning_rules():
    # Construct a dirty dataframe
    dates = pd.date_range("2023-01-01", periods=6, freq="D")
    df = pd.DataFrame({
        "Open": [100, -10, 102, np.nan, np.nan, 105], # row 1 is negative, row 3,4 is nan
        "High": [105, 106, 107, np.nan, np.nan, 109],
        "Low": [95, 96, 97, np.nan, np.nan, 99],
        "Close": [101, 102, 103, np.nan, np.nan, 105],
    }, index=dates)
    
    # Add a duplicate
    df = pd.concat([df, df.iloc[[-1]]])
    
    cleaned = clean_ohlcv(df, "TEST")
    
    assert len(cleaned) == 5 # 6 original + 1 dupe = 7. Drop dupe -> 6. Drop row 1 (-10) -> 5. NaNs ffilled -> 5.
    assert cleaned.index.is_unique
    assert (cleaned["Open"] > 0).all()
    # Check ffill worked for the NaNs
    assert cleaned.loc["2023-01-04", "Close"] == 103 # Ffilled from Jan 3

def test_loader_seed_fallback(mock_data_dir, sample_ohlcv):
    # Live is blocked by conftest. Cache is empty. Seed exists.
    seed_path = os.path.join(mock_data_dir["seed_dir"], "TEST.csv")
    sample_ohlcv.to_csv(seed_path)
    
    res = load_data("TEST")
    assert res.source == "seed"
    assert res.fetched_at == "seed_snapshot"
    assert len(res.df) == 5

def test_loader_cache_fallback(mock_data_dir, sample_ohlcv):
    # Put in cache
    cache_path = os.path.join(mock_data_dir["cache_dir"], "TEST.parquet")
    sample_ohlcv.to_parquet(cache_path)
    
    res = load_data("TEST")
    assert res.source == "cache"
    assert "T" in res.fetched_at # Should be ISO format string
