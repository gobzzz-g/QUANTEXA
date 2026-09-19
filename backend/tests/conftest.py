import pytest
import yfinance as yf
import os
import pandas as pd

@pytest.fixture(autouse=True)
def disable_yfinance(monkeypatch):
    def mock_download(*args, **kwargs):
        raise RuntimeError("Network access blocked in tests!")
    monkeypatch.setattr(yf, "download", mock_download)

@pytest.fixture
def mock_data_dir(tmp_path, monkeypatch):
    from app.config import settings
    cache_dir = tmp_path / "cache"
    seed_dir = tmp_path / "seed"
    cache_dir.mkdir()
    seed_dir.mkdir()
    
    monkeypatch.setattr(settings, "cache_dir", str(cache_dir))
    monkeypatch.setattr(settings, "seed_dir", str(seed_dir))
    
    return {"cache_dir": str(cache_dir), "seed_dir": str(seed_dir)}

@pytest.fixture
def sample_ohlcv():
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    df = pd.DataFrame({
        "Open": [100, 101, 102, 103, 104],
        "High": [105, 106, 107, 108, 109],
        "Low": [95, 96, 97, 98, 99],
        "Close": [101, 102, 103, 104, 105],
        "Volume": [1000]*5
    }, index=dates)
    return df
