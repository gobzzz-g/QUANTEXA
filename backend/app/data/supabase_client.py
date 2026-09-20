import os
from supabase import create_client, Client
from dotenv import load_dotenv
import pandas as pd
import logging

logger = logging.getLogger(__name__)

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    logger.warning("Supabase credentials not found. Ensure SUPABASE_URL and SUPABASE_KEY are set.")
    supabase = None

def normalize_ticker(t: str) -> str:
    t_clean = str(t).upper().strip()
    if t_clean in ["BTC-USD", "BTC", "BITCOIN", "BITCOINS"]:
        return "BTC"
    if t_clean in ["GC=F", "GOLD", "GOLDFUTURES", "GLD"]:
        return "GOLD"
    if t_clean in ["NVDA", "NVIDIA"]:
        return "NVDA"
    return t_clean

def get_asset_prices(asset_ticker: str) -> pd.DataFrame:
    """
    Fetches historical prices for an asset from Supabase.
    Resolves ticker aliases (e.g. BTC-USD -> BTC, GC=F -> GOLD).
    """
    if not supabase:
        raise ValueError("Supabase client not initialized")
        
    norm_ticker = normalize_ticker(asset_ticker)
    
    # Try searching by symbol or source_dataset
    res = supabase.table('assets').select('id, symbol, source_dataset').eq('symbol', norm_ticker).execute()
    if not res.data:
        res = supabase.table('assets').select('id, symbol, source_dataset').eq('symbol', asset_ticker).execute()
    if not res.data:
        res = supabase.table('assets').select('id, symbol, source_dataset').eq('source_dataset', asset_ticker).execute()
        
    if not res.data:
        raise ValueError(f"Asset {asset_ticker} not found in Supabase assets table")
        
    asset_id = res.data[0]['id']
    
    # Now fetch prices
    prices_res = supabase.table('market_prices').select('*').eq('asset_id', asset_id).order('date').execute()
    
    if not prices_res.data:
        return pd.DataFrame()
        
    df = pd.DataFrame(prices_res.data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    rename_map = {
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    }
    df.rename(columns=rename_map, inplace=True)
    return df

def get_all_assets() -> dict:
    """
    Fetches all available assets from Supabase and config settings,
    providing unified aliases for Bitcoin, Gold, and NVIDIA.
    """
    from ..config import settings
    assets_dict = {k: v.dict() for k, v in settings.assets.items()}
    
    if supabase:
        try:
            res = supabase.table('assets').select('*').execute()
            if res.data:
                for row in res.data:
                    sym = row.get('symbol') or ''
                    name = row.get('name') or sym
                    asset_type = row.get('asset_type', '')
                    calendar_days = 365 if str(asset_type).upper() == 'CRYPTOCURRENCY' else 252
                    
                    if sym:
                        assets_dict[sym] = {
                            "ticker": sym,
                            "name": name,
                            "calendar_days": calendar_days,
                            "asset_class": asset_type
                        }
                    # Also register common canonical forms
                    if sym == "BTC":
                        assets_dict["BTC-USD"] = {"ticker": "BTC-USD", "name": "Bitcoin", "calendar_days": 365, "asset_class": "CRYPTOCURRENCY"}
                    elif sym == "GOLD":
                        assets_dict["GC=F"] = {"ticker": "GC=F", "name": "Gold (COMEX)", "calendar_days": 252, "asset_class": "COMMODITY"}
                        assets_dict["GLD"] = {"ticker": "GLD", "name": "Gold ETF (GLD)", "calendar_days": 252, "asset_class": "COMMODITY"}
                    elif sym == "NVDA":
                        assets_dict["NVDA"] = {"ticker": "NVDA", "name": "NVIDIA", "calendar_days": 252, "asset_class": "EQUITY"}
        except Exception as e:
            logger.warning(f"Error fetching assets from Supabase: {e}")
            
    return assets_dict

from typing import List, Dict

def get_multiple_asset_prices(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Fetches historical prices for multiple assets from Supabase in batched queries.
    """
    if not supabase:
        raise ValueError("Supabase client not initialized")
    
    if not tickers:
        return {}
        
    # Batch resolve asset UUIDs
    res = supabase.table('assets').select('id, symbol, source_dataset').in_('source_dataset', tickers).execute()
    
    found_assets = res.data or []
    found_tickers = {row['source_dataset'] for row in found_assets}
    
    missing_tickers = set(tickers) - found_tickers
    if missing_tickers:
        res2 = supabase.table('assets').select('id, symbol, source_dataset').in_('symbol', list(missing_tickers)).execute()
        found_assets.extend(res2.data or [])
        
    if not found_assets:
        return {t: pd.DataFrame() for t in tickers}
        
    asset_id_to_ticker = {}
    for row in found_assets:
        ticker = row['source_dataset'] if row['source_dataset'] in tickers else row['symbol']
        asset_id_to_ticker[row['id']] = ticker
        
    asset_ids = list(asset_id_to_ticker.keys())
    
    # Now fetch prices for all found assets
    prices_res = supabase.table('market_prices').select('asset_id, date, close, open, high, low, volume').in_('asset_id', asset_ids).order('date').execute()
    
    if not prices_res.data:
        return {t: pd.DataFrame() for t in tickers}
        
    df = pd.DataFrame(prices_res.data)
    df['date'] = pd.to_datetime(df['date'])
    
    # Rename columns
    rename_map = {
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    }
    df.rename(columns=rename_map, inplace=True)
    
    result = {}
    for asset_id, group in df.groupby('asset_id'):
        ticker = asset_id_to_ticker.get(asset_id)
        if ticker:
            group_df = group.drop(columns=['asset_id']).set_index('date')
            result[ticker] = group_df
            
    # Fill missing ones with empty dfs
    for t in tickers:
        if t not in result:
            result[t] = pd.DataFrame()
            
    return result
