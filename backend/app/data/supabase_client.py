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

def get_asset_prices(asset_ticker: str) -> pd.DataFrame:
    """
    Fetches historical prices for an asset from Supabase.
    We first resolve the asset UUID from the `assets` table based on the ticker (source_dataset),
    and then fetch the prices from `market_prices`.
    """
    if not supabase:
        raise ValueError("Supabase client not initialized")
        
    # In the schema, the ticker might map to `symbol` or `source_dataset`
    # Let's search by `source_dataset` which contains things like GC=F
    res = supabase.table('assets').select('id, symbol, source_dataset').eq('source_dataset', asset_ticker).execute()
    
    if not res.data:
        # Fallback to symbol
        res = supabase.table('assets').select('id, symbol, source_dataset').eq('symbol', asset_ticker).execute()
        
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
    
    # Rename columns to match existing convention if needed (e.g. Open, High, Low, Close, Volume)
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
    Fetches all available assets from Supabase and returns them
    in the format expected by the frontend.
    """
    if not supabase:
        # Fallback to local settings if Supabase isn't configured
        from ..config import settings
        return {k: v.dict() for k, v in settings.assets.items()}
        
    res = supabase.table('assets').select('*').execute()
    if not res.data:
        from ..config import settings
        return {k: v.dict() for k, v in settings.assets.items()}
        
    assets_dict = {}
    for row in res.data:
        ticker = row['source_dataset'] or row['symbol']
        name = row['name'] or ticker
        asset_type = row.get('asset_type', '')
        # Determine calendar days based on type
        calendar_days = 365 if str(asset_type).upper() == 'CRYPTOCURRENCY' else 252
        
        assets_dict[ticker] = {
            "ticker": ticker,
            "name": name,
            "calendar_days": calendar_days,
            "asset_class": asset_type
        }
        
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
