from pydantic import BaseModel
from typing import Dict, Literal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class AssetConfig(BaseModel):
    ticker: str
    name: str
    calendar_days: int  # 252 or 365

class AppSettings(BaseModel):
    assets: Dict[str, AssetConfig] = {
        "BTC-USD": AssetConfig(ticker="BTC-USD", name="Bitcoin", calendar_days=365),
        "GC=F": AssetConfig(ticker="GC=F", name="Gold (COMEX)", calendar_days=252),
        "NVDA": AssetConfig(ticker="NVDA", name="NVIDIA", calendar_days=252),
        "GLD": AssetConfig(ticker="GLD", name="Gold ETF (GLD)", calendar_days=252),
    }
    
    # Paths
    cache_dir: str = str(BASE_DIR / "data" / "cache")
    seed_dir: str = str(BASE_DIR / "data" / "seed")

settings = AppSettings()
