import logging
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from ..config import settings
from ..data.loader import load_data
from ..data.supabase_client import get_all_assets
from ..indicators.metrics import calc_sma, calc_ema, calc_drawdown, calc_sharpe, calc_annualized_volatility, calc_calmar, calc_sortino
from ..strategies.base import SMACrossover, EMATrend, Momentum, MeanReversion
from ..backtest.engine import BacktestEngine
from ..regimes.analysis import label_bull_bear, label_volatility
from ..robustness.sensitivity import run_parameter_grid
from ..correlation.analyzer import compute_correlation_matrix

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/assets")
def get_assets(batch_id: Optional[str] = None):
    if not batch_id:
        return get_all_assets()
    from ..agent.financial_agent import financial_agent
    client = financial_agent._ensure_client()
    assets_data = financial_agent.get_batch_assets(batch_id)
    if not assets_data:
        try:
            stat_res = (
                client.table("asset_statistics")
                .select("asset_id, assets(id, symbol, name, asset_type)")
                .eq("batch_id", batch_id)
                .execute()
            )
            seen = set()
            for row in (stat_res.data or []):
                a = row.get("assets")
                if a and a.get("symbol") not in seen:
                    seen.add(a.get("symbol"))
                    assets_data.append({
                        "asset_id": a.get("id"),
                        "symbol": a.get("symbol"),
                        "name": a.get("name"),
                        "asset_type": a.get("asset_type"),
                    })
        except Exception:
            pass
    res = {}
    for a in assets_data:
        sym = a["symbol"]
        res[sym] = {
            "ticker": sym,
            "name": a.get("name") or sym,
            "calendar_days": 365 if a.get("asset_type") == "CRYPTOCURRENCY" else 252,
            "asset_class": a.get("asset_type") or "Unknown",
        }
    return res

def _get_provenance(ticker: str, assets: dict = None):
    res = load_data(ticker)
    if res.df.empty:
        raise HTTPException(400, "Empty data for asset")
    assets = assets or get_all_assets()
    cfg = assets.get(ticker)
    
    return {
        "ticker": ticker,
        "instrument_name": cfg["name"] if cfg else ticker,
        "data_source": res.source,
        "first_bar": res.df.index[0].strftime("%Y-%m-%d"),
        "last_bar": res.df.index[-1].strftime("%Y-%m-%d"),
        "fetched_at": res.fetched_at
    }, res.df

@router.get("/prices")
def get_prices(asset: str = "BTC-USD"):
    assets = get_all_assets()
    if asset not in assets:
        raise HTTPException(404, "Asset not found")
    prov, df = _get_provenance(asset, assets)
    
    return {
        "provenance": prov,
        "dates": df.index.strftime("%Y-%m-%d").tolist(),
        "open": df['Open'].tolist(),
        "high": df['High'].tolist(),
        "low": df['Low'].tolist(),
        "close": df['Close'].tolist(),
        "volume": df['Volume'].tolist(),
        "rebased": (df['Close'] / df['Close'].iloc[0] * 100).tolist()
    }

class BacktestRequest(BaseModel):
    asset: str
    strategy: str
    params: Dict[str, float]
    initial_capital: float = 10000.0
    commission_pct: float = 0.001
    slippage_bps: float = 5.0
    position_sizing: float = 1.0
    risk_free_rate: float = 0.0

@router.post("/backtest")
def run_backtest(req: BacktestRequest):
    assets = get_all_assets()
    if req.asset not in assets:
        raise HTTPException(404, "Asset not found")
        
    prov, df = _get_provenance(req.asset, assets)
    
    if req.strategy == "sma_crossover":
        strat = SMACrossover(int(req.params.get('fast', 20)), int(req.params.get('slow', 50)))
    elif req.strategy == "ema_trend":
        strat = EMATrend(int(req.params.get('fast', 12)), int(req.params.get('slow', 26)))
    elif req.strategy == "momentum":
        strat = Momentum(int(req.params.get('lookback', 90)), float(req.params.get('threshold', 0.0)))
    elif req.strategy == "mean_reversion":
        strat = MeanReversion(int(req.params.get('lookback', 20)), float(req.params.get('z_enter', -2.0)), float(req.params.get('z_exit', 0.0)))
    else:
        raise HTTPException(400, "Unknown strategy")
        
    signal = strat.generate_positions(df)
    ann_factor = assets[req.asset]["calendar_days"]
    
    engine = BacktestEngine(
        df, signal, ann_factor,
        initial_capital=req.initial_capital,
        commission_pct=req.commission_pct,
        slippage_bps=req.slippage_bps,
        position_sizing=req.position_sizing,
        risk_free_rate=req.risk_free_rate
    )
    
    res = engine.run()
    res["provenance"] = prov
    return res

@router.get("/regimes")
def get_regimes(asset: str = "BTC-USD"):
    assets = get_all_assets()
    if asset not in assets:
        raise HTTPException(404, "Asset not found")
    prov, df = _get_provenance(asset, assets)
    
    bull_bear = label_bull_bear(df)
    volatility = label_volatility(df)
    
    return {
        "provenance": prov,
        "dates": df.index.strftime("%Y-%m-%d").tolist(),
        "bull_bear": bull_bear.tolist(),
        "volatility": volatility.tolist()
    }

@router.get("/robustness")
def get_robustness(asset: str, strategy: str, batch_id: Optional[str] = None):
    # If batch_id is provided, query the Layer 5 robustness_results table in Supabase
    if batch_id:
        try:
            from ..agent.financial_agent import financial_agent
            client = financial_agent._ensure_client()
            clean_asset = asset.replace("-USD", "").strip().upper()
            clean_strat = strategy.upper().replace("-", "_")
            
            query = (
                client.table("robustness_results")
                .select("*, assets!inner(symbol, name)")
                .eq("batch_id", batch_id)
                .ilike("strategy_name", clean_strat)
            )
            
            if len(clean_asset) == 36 and "-" in clean_asset:
                query = query.eq("asset_id", clean_asset)
            else:
                query = query.eq("assets.symbol", clean_asset)
                
            res = query.order("id").execute()
            rows = res.data or []
            
            formatted_results = []
            for r in rows:
                formatted_results.append({
                    "id": r.get("id"),
                    "parameters": r.get("parameters") or {},
                    "annualized_return": float(r.get("annualized_return") or 0.0),
                    "total_return": float(r.get("total_return") or 0.0),
                    "sharpe": float(r.get("sharpe_ratio") or 0.0),
                    "max_drawdown": float(r.get("max_drawdown") or 0.0),
                    "trades": int(r.get("trades") or 0),
                    "win_rate": float(r.get("win_rate") or 0.0),
                    "test_type": r.get("test_type", "PARAMETER"),
                    "test_value": r.get("test_value"),
                    # For backwards compatibility with legacy consumers:
                    "cagr": float(r.get("annualized_return") or 0.0),
                })
                
            return {
                "batch_id": batch_id,
                "asset": clean_asset,
                "strategy": clean_strat,
                "count": len(formatted_results),
                "results": formatted_results
            }
        except Exception as e:
            logger.error(f"Error in get_robustness for {batch_id}: {e}", exc_info=True)
            raise HTTPException(500, detail=str(e))

    assets = get_all_assets()
    if asset not in assets:
        raise HTTPException(404, "Asset not found")
    prov, df = _get_provenance(asset, assets)
    
    results = run_parameter_grid(df, asset, strategy)
    return {
        "provenance": prov,
        "results": results
    }

@router.get("/metrics")
def get_metrics(asset: str = "BTC-USD"):
    assets = get_all_assets()
    if asset not in assets:
        raise HTTPException(404, "Asset not found")
    prov, df = _get_provenance(asset, assets)
    
    if df.empty:
        raise HTTPException(400, "Empty data for asset")
        
    prices = df['Close']
    returns = prices.pct_change().dropna()
    N = assets[asset]["calendar_days"]
    
    cagr = (prices.iloc[-1] / prices.iloc[0]) ** (1 / (len(prices) / N)) - 1 if len(prices) > 2 else 0.0
    vol = calc_annualized_volatility(returns, N)
    sharpe = calc_sharpe(returns, N)
    _, max_dd = calc_drawdown(prices)
    
    return {
        "provenance": prov,
        "cagr": cagr,
        "annualized_volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "current_price": float(prices.iloc[-1]) if not prices.empty else 0.0
    }

@router.get("/indicators")
def get_indicators(asset: str = "BTC-USD", window: int = 20):
    assets = get_all_assets()
    if asset not in assets:
        raise HTTPException(404, "Asset not found")
    prov, df = _get_provenance(asset, assets)
    if df.empty:
        raise HTTPException(400, "Empty data for asset")
    close = df['Close']
    sma = calc_sma(close, window)
    ema = calc_ema(close, window)
    latest_close = float(close.iloc[-1])
    latest_sma = float(sma.dropna().iloc[-1]) if not sma.dropna().empty else latest_close
    latest_ema = float(ema.dropna().iloc[-1]) if not ema.dropna().empty else latest_close
    pct_diff = ((latest_close - latest_sma) / latest_sma * 100) if latest_sma != 0 else 0.0
    
    return {
        "asset": asset,
        "provenance": prov,
        "window": window,
        "latest_close": latest_close,
        "latest_sma": latest_sma,
        "latest_ema": latest_ema,
        "pct_diff_sma": pct_diff
    }

@router.get("/correlation")
def get_correlation(batch_id: Optional[str] = None):
    if batch_id:
        return fa_batch_correlation_analysis(batch_id=batch_id, window="full")
    # If no batch_id passed, check for TEST_BATCH_01 first, then any completed batch with assets
    try:
        res = fa_batch_correlation_analysis(batch_id="TEST_BATCH_01", window="full")
        if res.get("assets") and len(res["assets"]) >= 2:
            return res
    except Exception:
        pass
    try:
        client = financial_agent._ensure_client()
        b_res = client.table("analysis_batches").select("batch_id").eq("status", "COMPLETED").order("created_at", desc=True).execute()
        for b in (b_res.data or []):
            res = fa_batch_correlation_analysis(batch_id=b["batch_id"], window="full")
            if res.get("assets") and len(res["assets"]) >= 2:
                return res
    except Exception:
        pass

    dfs = {}
    canonical_symbols = ["BTC", "GOLD", "NVDA"]
    assets = get_all_assets()
    for asset in canonical_symbols:
        if asset in assets:
            try:
                _, df = _get_provenance(asset, assets)
                if not df.empty:
                    dfs[asset] = df
            except Exception:
                pass
            
    if not dfs:
        raise HTTPException(400, "No data available for correlation")
        
    corr_matrix = compute_correlation_matrix(dfs)
    
    return {
        "assets": list(corr_matrix.columns),
        "matrix": corr_matrix.values.tolist()
    }


class PortfolioRequest(BaseModel):
    assets: List[str]
    method: str = "max_sharpe"
    risk_free_rate: float = 0.0
    use_quantum_baseline: bool = False

from ..optimization.portfolio import optimize_portfolio
from ..optimization.quantum import optimize_portfolio_qubo
import pandas as pd

@router.post("/portfolio")
def run_portfolio_optimization(req: PortfolioRequest):
    if len(req.assets) < 2:
        raise HTTPException(400, "At least two assets required for portfolio optimization")
        
    dfs = {}
    assets = get_all_assets()
    for asset in req.assets:
        if asset not in assets:
            raise HTTPException(404, f"Asset not found: {asset}")
        try:
            _, df = _get_provenance(asset, assets)
            if not df.empty:
                dfs[asset] = df
        except Exception:
            raise HTTPException(400, f"No data available for {asset}")
            
    # Calculate expected returns and covariance matrix
    # Using annualized metrics
    prices_df = pd.DataFrame({asset: df['Close'] for asset, df in dfs.items()}).dropna()
    if prices_df.empty:
        raise HTTPException(400, "No overlapping data for selected assets")
        
    returns_df = prices_df.pct_change().dropna()
    N = 252 # Assumes trading days for simplicity
    
    expected_returns = returns_df.mean() * N
    cov_matrix = returns_df.cov() * N
    
    if req.use_quantum_baseline:
        result = optimize_portfolio_qubo(expected_returns, cov_matrix, risk_aversion=0.5)
    else:
        result = optimize_portfolio(expected_returns, cov_matrix, req.method, req.risk_free_rate)
        
    return {
        "assets": req.assets,
        "optimization": result,
        "cov_matrix": cov_matrix.values.tolist(),
        "expected_returns": expected_returns.to_dict()
    }

from ..knowledge.graph import get_full_graph, get_entity_context

@router.get("/graph")
def get_graph():
    return get_full_graph()

@router.get("/graph/{entity_id}")
def get_node_context(entity_id: str):
    context = get_entity_context(entity_id)
    if not context:
        raise HTTPException(404, "Entity not found in Knowledge Graph")
    return context

class ResearchRequest(BaseModel):
    query: str
    assets: Optional[List[str]] = None
    batch_id: Optional[str] = None

from ..agent.research import run_research_query

@router.post("/research")
def research_endpoint(req: ResearchRequest):
    return run_research_query(req.query, req.assets, req.batch_id)

import pandas as pd


def compute_batch_market_analysis(batch_id: str, lookback: str = "1Y"):
    """
    Computes cross-asset market analysis strictly scoped to the selected batch.
    Uses real Supabase market_prices (Layer 1) and asset_statistics (Layer 2).
    """
    from ..agent.financial_agent import financial_agent
    client = financial_agent._ensure_client()

    # 1. Resolve batch assets
    assets_data = financial_agent.get_batch_assets(batch_id)
    if not assets_data:
        try:
            stat_res = (
                client.table("asset_statistics")
                .select("asset_id, assets(id, symbol, name, asset_type)")
                .eq("batch_id", batch_id)
                .execute()
            )
            seen = set()
            for row in (stat_res.data or []):
                a = row.get("assets")
                if a and a.get("symbol") not in seen:
                    seen.add(a.get("symbol"))
                    assets_data.append({
                        "asset_id": a.get("id"),
                        "symbol": a.get("symbol"),
                        "name": a.get("name"),
                        "asset_type": a.get("asset_type"),
                    })
        except Exception as e:
            logger.warning(f"Fallback asset lookup failed for {batch_id}: {e}")

    if not assets_data:
        return {
            "batch_id": batch_id,
            "chart_data": {},
            "breadth": {
                "advancing": 0,
                "declining": 0,
                "unchanged": 0,
                "total": 0,
                "ad_ratio": "0.00",
            },
            "monitor": [],
            "kpis": {
                "tracked_assets": 0,
                "advancing": 0,
                "declining": 0,
                "unchanged": 0,
                "avg_period_return": 0.0,
                "highest_performer": "-",
                "highest_period_return": 0.0,
                "lowest_performer": "-",
                "lowest_period_return": 0.0,
                "data_through": "-",
                "lookback": lookback,
            },
        }

    # 2. Fetch Layer 2 annualized volatility from asset_statistics
    vol_map = {}
    try:
        stat_res = (
            client.table("asset_statistics")
            .select("asset_id, annualized_volatility")
            .eq("batch_id", batch_id)
            .execute()
        )
        for row in (stat_res.data or []):
            vol_map[row["asset_id"]] = float(row.get("annualized_volatility") or 0.0)
    except Exception as e:
        logger.warning(f"Failed to fetch asset_statistics for {batch_id}: {e}")

    # 3. Find latest price and previous close per asset to compute daily return
    asset_latest_info = {}
    all_latest_dates = []
    for a in assets_data:
        a_id = a["asset_id"]
        try:
            pr = (
                client.table("market_prices")
                .select("date, close")
                .eq("asset_id", a_id)
                .order("date", desc=True)
                .limit(10)
                .execute()
            )
            by_date = {}
            for r in (pr.data or []):
                if r["date"] not in by_date:
                    by_date[r["date"]] = float(r["close"] or 0.0)
            sorted_dates = sorted(by_date.keys(), reverse=True)
            if sorted_dates:
                latest_d = sorted_dates[0]
                latest_c = by_date[latest_d]
                prev_c = by_date[sorted_dates[1]] if len(sorted_dates) > 1 else latest_c
                daily_ret = (latest_c - prev_c) / prev_c if prev_c != 0 else 0.0
                asset_latest_info[a_id] = {
                    "latest_date": latest_d,
                    "latest_close": latest_c,
                    "prev_close": prev_c,
                    "daily_return": daily_ret,
                }
                all_latest_dates.append(latest_d)
        except Exception as e:
            logger.warning(f"Error fetching latest prices for {a.get('symbol')}: {e}")

    overall_latest_date = max(all_latest_dates) if all_latest_dates else None

    # 4. Determine lookback cutoff date relative to overall_latest_date
    from datetime import datetime as dt, timedelta
    cutoff_str = "1900-01-01"
    if overall_latest_date and lookback != "MAX":
        latest_dt = dt.strptime(overall_latest_date, "%Y-%m-%d")
        if lookback == "1M":
            cutoff_dt = latest_dt - timedelta(days=30)
        elif lookback == "3M":
            cutoff_dt = latest_dt - timedelta(days=90)
        elif lookback == "6M":
            cutoff_dt = latest_dt - timedelta(days=180)
        elif lookback == "1Y":
            cutoff_dt = latest_dt - timedelta(days=365)
        else:
            cutoff_dt = latest_dt - timedelta(days=365)
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d")

    # 5. Fetch price series for the period
    chart_data = {}
    monitor = []
    advancing = 0
    declining = 0
    unchanged = 0

    for a in assets_data:
        a_id = a["asset_id"]
        sym = a["symbol"]
        name = a.get("name") or sym
        asset_class = a.get("asset_type") or "Unknown"

        latest_info = asset_latest_info.get(a_id, {})
        current_price = latest_info.get("latest_close", 0.0)
        daily_ret = latest_info.get("daily_return", 0.0)

        # Market Breadth using latest daily return:
        # Explicit unchanged threshold: abs(daily_return) <= 0.0001 (0.01%)
        if daily_ret > 0.0001:
            advancing += 1
        elif daily_ret < -0.0001:
            declining += 1
        else:
            unchanged += 1

        try:
            if lookback == "MAX":
                all_rows = []
                offset = 0
                while True:
                    res = (
                        client.table("market_prices")
                        .select("date, close")
                        .eq("asset_id", a_id)
                        .order("date", desc=False)
                        .range(offset, offset + 999)
                        .execute()
                    )
                    data = res.data or []
                    all_rows.extend(data)
                    if len(data) < 1000:
                        break
                    offset += 1000
                rows = all_rows
            else:
                res = (
                    client.table("market_prices")
                    .select("date, close")
                    .eq("asset_id", a_id)
                    .gte("date", cutoff_str)
                    .order("date", desc=False)
                    .range(0, 999)
                    .execute()
                )
                rows = res.data or []

            by_date = {}
            for r in rows:
                by_date[r["date"]] = float(r["close"] or 0.0)
            dates = sorted(by_date.keys())
            closes = [by_date[d] for d in dates]

            if closes:
                start_p = closes[0]
                end_p = closes[-1]
                period_ret = (end_p - start_p) / start_p if start_p != 0 else 0.0
                base = start_p if start_p != 0 else 1.0
                rebased = [round((c / base) * 100, 4) for c in closes]
                chart_data[sym] = {
                    "dates": dates,
                    "rebased": rebased,
                    "name": name,
                }
            else:
                period_ret = 0.0
        except Exception as e:
            logger.warning(f"Error building price series for {sym}: {e}")
            period_ret = 0.0

        monitor.append({
            "symbol": sym,
            "name": name,
            "asset_class": asset_class,
            "current_price": current_price,
            "daily_return": daily_ret,
            "period_return": period_ret,
            "volatility": vol_map.get(a_id, 0.0),
        })

    if declining == 0:
        ad_ratio = "∞" if advancing > 0 else "0.00"
    else:
        ad_ratio = f"{(advancing / declining):.2f}"

    period_returns = [m["period_return"] for m in monitor]
    avg_period_ret = sum(period_returns) / len(period_returns) if period_returns else 0.0
    highest_perf = max(monitor, key=lambda x: x["period_return"]) if monitor else None
    lowest_perf = min(monitor, key=lambda x: x["period_return"]) if monitor else None

    return {
        "batch_id": batch_id,
        "chart_data": chart_data,
        "breadth": {
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "total": advancing + declining + unchanged,
            "ad_ratio": ad_ratio,
        },
        "monitor": monitor,
        "kpis": {
            "tracked_assets": len(assets_data),
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "avg_period_return": avg_period_ret,
            "highest_performer": highest_perf["name"] if highest_perf else "-",
            "highest_period_return": highest_perf["period_return"] if highest_perf else 0.0,
            "lowest_performer": lowest_perf["name"] if lowest_perf else "-",
            "lowest_period_return": lowest_perf["period_return"] if lowest_perf else 0.0,
            "data_through": overall_latest_date or "-",
            "lookback": lookback,
        },
    }


@router.get("/market-analysis")
def get_market_analysis(lookback: str = "1Y", batch_id: Optional[str] = None):
    if batch_id:
        return compute_batch_market_analysis(batch_id, lookback)
    try:
        from ..agent.financial_agent import financial_agent
        batches = financial_agent.list_analysis_batches()
        if batches:
            return compute_batch_market_analysis(batches[0]["batch_id"], lookback)
    except Exception:
        pass
    return compute_batch_market_analysis("TEST_BATCH_01", lookback)


@router.get("/financial-agent/batch/{batch_id}/market-analysis")
def fa_batch_market_analysis(batch_id: str, lookback: str = "1Y"):
    return compute_batch_market_analysis(batch_id, lookback)

from ..data.loader import load_overview_data

@router.get("/overview")
def get_overview():
    assets = get_all_assets()
    tickers = list(assets.keys())
    
    if not tickers:
        return {"assets": {}, "metrics": {}, "prices": {}}
        
    data_results = load_overview_data(tickers)
    
    metrics_res = {}
    prices_res = {}
    
    for ticker in tickers:
        d_res = data_results.get(ticker)
        if not d_res or d_res.df.empty:
            continue
            
        df = d_res.df
        prov = {
            "ticker": ticker,
            "instrument_name": assets[ticker]["name"],
            "data_source": d_res.source,
            "first_bar": df.index[0].strftime("%Y-%m-%d"),
            "last_bar": df.index[-1].strftime("%Y-%m-%d"),
            "fetched_at": d_res.fetched_at
        }
        
        # Calculate metrics
        prices_series = df['Close']
        returns = prices_series.pct_change().dropna()
        N = assets[ticker]["calendar_days"]
        
        cagr = (prices_series.iloc[-1] / prices_series.iloc[0]) ** (1 / (len(prices_series) / N)) - 1 if len(prices_series) > 2 else 0.0
        vol = calc_annualized_volatility(returns, N)
        sharpe = calc_sharpe(returns, N)
        _, max_dd = calc_drawdown(prices_series)
        
        metrics_res[ticker] = {
            "provenance": prov,
            "cagr": cagr,
            "annualized_volatility": vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "current_price": float(prices_series.iloc[-1]) if not prices_series.empty else 0.0
        }
        
        # Calculate prices for chart
        prices_res[ticker] = {
            "provenance": prov,
            "dates": df.index.strftime("%Y-%m-%d").tolist(),
            "rebased": (prices_series / prices_series.iloc[0] * 100).tolist()
        }
        
    return {
        "assets": assets,
        "metrics": metrics_res,
        "prices": prices_res
    }

# ---------------------------------------------------------------------------
# 7-Layer Financial Pipeline & Knowledge Graph Integration Endpoints
# ---------------------------------------------------------------------------
from pathlib import Path
import sys

PIPELINE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "financial-data-pipeline"
if str(PIPELINE_PATH) not in sys.path:
    sys.path.insert(0, str(PIPELINE_PATH))

@router.get("/pipeline/batches")
def list_pipeline_batches():
    """Retrieve all analysis batches and their execution statuses."""
    try:
        import kg_pipeline_bridge
        client = kg_pipeline_bridge.get_supabase_client()
        res = client.table("analysis_batches").select("*").order("created_at", desc=True).execute()
        return {"batches": res.data or []}
    except Exception as e:
        raise HTTPException(500, f"Error listing pipeline batches: {e}")

@router.get("/pipeline/summary")
def get_pipeline_summary(batch_id: str = "TEST_BATCH_01"):
    """Retrieve full 7-layer quantitative metrics and results for a given batch."""
    try:
        import kg_pipeline_bridge
        client = kg_pipeline_bridge.get_supabase_client()
        
        # Batch info
        b_res = client.table("analysis_batches").select("*").eq("batch_id", batch_id).execute().data
        batch_info = b_res[0] if b_res else {"batch_id": batch_id, "status": "UNKNOWN"}
        
        # L1/L2: Assets & Stats
        stats = client.table("asset_statistics").select("*, assets(symbol, asset_type)").eq("batch_id", batch_id).execute().data
        assets_summary = []
        for s in stats:
            sym = s.get("assets", {}).get("symbol") if s.get("assets") else "UNKNOWN"
            assets_summary.append({
                "symbol": sym,
                "annualized_return": s.get("annualized_return"),
                "annualized_volatility": s.get("annualized_volatility"),
                "sharpe_ratio": s.get("sharpe_ratio"),
                "max_drawdown": s.get("max_drawdown")
            })
            
        # L3: Signals count
        signals_cnt = client.table("strategy_signals").select("id", count="exact").eq("batch_id", batch_id).limit(1).execute().count
        
        # L4: Backtest runs & metrics
        bt_runs = client.table("backtest_runs").select("id, strategy_name, assets(symbol)").eq("batch_id", batch_id).execute().data
        backtests = []
        for btr in bt_runs:
            m_res = client.table("backtest_metrics").select("metric_name, metric_value").eq("backtest_run_id", btr["id"]).execute().data
            m_map = {m["metric_name"]: m["metric_value"] for m in m_res}
            backtests.append({
                "strategy": btr.get("strategy_name"),
                "asset": btr.get("assets", {}).get("symbol") if btr.get("assets") else "UNKNOWN",
                "total_return": m_map.get("total_return"),
                "annualized_return": m_map.get("annualized_return"),
                "sharpe_ratio": m_map.get("sharpe_ratio"),
                "max_drawdown": m_map.get("max_drawdown"),
                "trades": m_map.get("total_trades", m_map.get("trade_count")),
                "win_rate": m_map.get("win_rate")
            })
            
        # L5: Market regimes
        regimes_data = client.table("market_regimes").select("regime").eq("batch_id", batch_id).execute().data
        regimes_counts = {}
        for r in regimes_data:
            lbl = r.get("regime", "UNKNOWN")
            regimes_counts[lbl] = regimes_counts.get(lbl, 0) + 1
            
        # L6: Portfolio allocations
        opt_runs = client.table("portfolio_optimization_runs").select("id, objective").eq("batch_id", batch_id).execute().data
        allocations = {}
        for r in opt_runs:
            allocs = client.table("portfolio_allocations").select("asset_symbol, continuous_weight, discrete_weight, expected_return, expected_volatility").eq("run_id", r["id"]).execute().data
            allocations[r.get("objective")] = allocs
            
        # L7: QUBO results
        qubo_runs = client.table("qubo_runs").select("id").eq("batch_id", batch_id).execute().data
        qubo_solutions = []
        for qr in qubo_runs:
            q_res = client.table("qubo_results").select("*").eq("qubo_run_id", qr["id"]).execute().data
            for sol in q_res:
                qubo_solutions.append(sol)
                
        return {
            "batch_info": batch_info,
            "layer_1_and_2_assets": assets_summary,
            "layer_3_signals_count": signals_cnt,
            "layer_4_backtest": backtests,
            "layer_5_regimes": regimes_counts,
            "layer_6_portfolio_allocations": allocations,
            "layer_7_qubo_results": qubo_solutions
        }
    except Exception as e:
        raise HTTPException(500, f"Error getting pipeline summary: {e}")

@router.post("/pipeline/sync-kg")
def sync_pipeline_knowledge_graph(batch_id: str = "TEST_BATCH_01"):
    """Trigger Neo4j Knowledge Graph synchronization for the 7-layer pipeline and batch."""
    try:
        import kg_pipeline_bridge
        res = kg_pipeline_bridge.sync_batch_to_neo4j(batch_id)
        return res
    except Exception as e:
        raise HTTPException(500, f"Error syncing pipeline to Knowledge Graph: {e}")


# ---------------------------------------------------------------------------
# UI Dataset Ingestion & Batch Lifecycle Endpoints
# ---------------------------------------------------------------------------
import io
import uuid
import hashlib
import threading

class DatasetPreviewRequest(BaseModel):
    filename: str
    content: str  # CSV text content

@router.post("/pipeline/preview-dataset")
def preview_dataset(req: DatasetPreviewRequest):
    """
    Parses and validates an uploaded CSV dataset before batch creation.
    Inspects columns, missing values, duplicates, and detects asset types.
    """
    try:
        if not req.content or not req.content.strip():
            raise HTTPException(400, "Uploaded CSV file is empty.")

        df = pd.read_csv(io.StringIO(req.content))
        if df.empty:
            raise HTTPException(400, "Uploaded CSV has no data rows.")

        columns = [str(c).strip() for c in df.columns]
        lower_cols = {c.lower(): c for c in columns}

        # Date column check
        date_col = lower_cols.get("date")
        if not date_col:
            raise HTTPException(400, f"Missing required 'date' column in CSV. Found: {columns}")

        # Asset column check
        asset_col = lower_cols.get("asset") or lower_cols.get("symbol") or lower_cols.get("ticker")
        if not asset_col:
            raise HTTPException(400, f"Missing required 'asset' or 'symbol' column in CSV. Found: {columns}")

        # Close price check
        close_col = lower_cols.get("close")
        if not close_col:
            raise HTTPException(400, f"Missing required 'close' column in CSV. Found: {columns}")

        # Basic metrics
        row_count = len(df)
        duplicate_rows = int(df.duplicated().sum())

        # Missing values per column
        missing_values = {col: int(df[col].isna().sum()) for col in columns}

        # Detected assets
        symbols = sorted([str(s).strip().upper() for s in df[asset_col].dropna().unique() if str(s).strip()])
        if not symbols:
            raise HTTPException(400, "No valid asset symbols found in the CSV.")

        # Date range
        try:
            parsed_dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
            date_range = {
                "start": str(parsed_dates.min().strftime("%Y-%m-%d")) if not parsed_dates.empty else None,
                "end": str(parsed_dates.max().strftime("%Y-%m-%d")) if not parsed_dates.empty else None
            }
        except Exception:
            date_range = {"start": None, "end": None}

        # Asset types resolution
        type_col = lower_cols.get("asset_type")
        detected_asset_types = {}
        missing_asset_types = []
        warnings = []

        # Known global mapping / existing DB lookup
        all_registered = get_all_assets()
        for sym in symbols:
            resolved_type = None
            if type_col and type_col in df.columns:
                m_types = df.loc[df[asset_col].astype(str).str.upper() == sym, type_col].dropna().astype(str).str.upper().unique()
                if len(m_types) == 1 and m_types[0] in ["EQUITY", "COMMODITY", "CRYPTOCURRENCY"]:
                    resolved_type = m_types[0]

            if not resolved_type:
                # Check registered assets
                if sym in all_registered and all_registered[sym].get("asset_class"):
                    resolved_type = str(all_registered[sym]["asset_class"]).upper()
                elif sym in ["BTC", "BTC-USD", "ETH", "SOL"]:
                    resolved_type = "CRYPTOCURRENCY"
                elif sym in ["GOLD", "GC=F", "GLD", "SLV"]:
                    resolved_type = "COMMODITY"
                elif sym in ["NVDA", "AAPL", "MSFT", "SPY", "QQQ"]:
                    resolved_type = "EQUITY"

            if resolved_type:
                detected_asset_types[sym] = resolved_type
            else:
                missing_asset_types.append(sym)

        # Invalid rows detection (negative prices, high < low)
        invalid_rows = 0
        if close_col and close_col in df.columns:
            close_num = pd.to_numeric(df[close_col], errors="coerce")
            invalid_rows += int((close_num < 0).sum())

        high_col = lower_cols.get("high")
        low_col = lower_cols.get("low")
        if high_col and low_col:
            h_num = pd.to_numeric(df[high_col], errors="coerce")
            l_num = pd.to_numeric(df[low_col], errors="coerce")
            invalid_rows += int((h_num < l_num).sum())

        return {
            "filename": req.filename,
            "row_count": row_count,
            "columns": columns,
            "detected_assets": symbols,
            "date_range": date_range,
            "missing_values": missing_values,
            "duplicate_rows": duplicate_rows,
            "invalid_rows": invalid_rows,
            "asset_types": detected_asset_types,
            "missing_asset_types": missing_asset_types,
            "can_proceed": True,
            "warnings": warnings
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error previewing dataset: {str(e)}")


class CreateBatchRequest(BaseModel):
    batch_name: str
    csv_filename: str
    csv_content: str
    asset_type_mappings: Optional[Dict[str, str]] = None


@router.post("/pipeline/create-batch")
def create_pipeline_batch(req: CreateBatchRequest):
    """
    Creates a new analysis batch with a UUID batch_id, stores dataset file safely,
    and inserts initial audit records into analysis_batches and batch_layer_runs.
    """
    try:
        from ..agent.financial_agent import financial_agent
        client = financial_agent._ensure_client()

        if not req.batch_name.strip():
            raise HTTPException(400, "Batch Name is required.")

        batch_id = str(uuid.uuid4())
        content_bytes = req.csv_content.encode("utf-8")
        dataset_hash = hashlib.sha256(content_bytes).hexdigest()

        # Save CSV file to data/uploads
        upload_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = f"{batch_id}_{req.csv_filename}"
        csv_path = upload_dir / safe_filename
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(req.csv_content)

        # 1. Register in analysis_batches
        batch_record = {
            "batch_id": batch_id,
            "batch_name": req.batch_name.strip(),
            "dataset_filename": req.csv_filename,
            "dataset_hash": dataset_hash,
            "status": "CREATED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_message": None,
            "config": {
                "csv_path": str(csv_path),
                "asset_type_mappings": req.asset_type_mappings or {}
            }
        }
        client.table("analysis_batches").insert(batch_record).execute()

        # 2. Initialize Layer 1 - 7 in batch_layer_runs
        layers_spec = [
            (1, "DATA INGESTION"),
            (2, "QUANTITATIVE ANALYSIS"),
            (3, "STRATEGY ENGINE"),
            (4, "BACKTESTING ENGINE"),
            (5, "ROBUSTNESS & REGIME ENGINE"),
            (6, "PORTFOLIO OPTIMIZATION"),
            (7, "QUBO OPTIMIZATION"),
        ]
        for l_num, l_name in layers_spec:
            client.table("batch_layer_runs").upsert({
                "batch_id": batch_id,
                "layer_number": l_num,
                "layer_name": l_name,
                "status": "NOT_STARTED",
                "started_at": None,
                "completed_at": None,
                "rows_processed": None,
                "error_message": None,
                "metadata": {}
            }, on_conflict="batch_id,layer_number").execute()

        return {
            "batch_id": batch_id,
            "batch_name": req.batch_name.strip(),
            "status": "CREATED",
            "dataset_filename": req.csv_filename,
            "dataset_hash": dataset_hash,
            "created_at": batch_record["created_at"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error creating analysis batch: {str(e)}")


class RunPipelineRequest(BaseModel):
    batch_id: str
    sync: bool = False


@router.post("/pipeline/run")
def trigger_pipeline_run(req: RunPipelineRequest):
    """
    Executes all 7 layers sequentially for the given batch_id.
    Can run synchronously or launch a tracked background execution.
    """
    from ..agent.financial_agent import financial_agent
    client = financial_agent._ensure_client()

    # Verify batch exists
    b_data = client.table("analysis_batches").select("*").eq("batch_id", req.batch_id).execute().data
    if not b_data:
        raise HTTPException(404, f"Analysis batch '{req.batch_id}' not found.")

    batch_info = b_data[0]
    config = batch_info.get("config") or {}
    csv_path = config.get("csv_path")
    asset_types = config.get("asset_type_mappings") or {}

    def _execute():
        try:
            import run_pipeline as runner
            runner.run_pipeline(
                batch_id=req.batch_id,
                csv_path=csv_path,
                asset_type_overrides=asset_types
            )
        except Exception as exc:
            import logging
            logging.getLogger("quantexa.pipeline").error(f"Pipeline error for {req.batch_id}: {exc}")

    if req.sync:
        _execute()
        # Return updated status
        return financial_agent.get_batch_status(req.batch_id)
    else:
        # Launch background thread
        thread = threading.Thread(target=_execute, daemon=True)
        thread.start()
        return {
            "batch_id": req.batch_id,
            "status": "RUNNING",
            "message": f"Pipeline analysis started for batch {req.batch_id}"
        }


@router.get("/pipeline/status/{batch_id}")
def get_pipeline_status(batch_id: str):
    """Retrieve live execution state and progress across Layers 1 to 7 for a batch."""
    from ..agent.financial_agent import financial_agent
    return financial_agent.get_batch_status(batch_id)


# ---------------------------------------------------------------------------
# Financial Agent API Bridge Endpoints (exposing 10 tools)
# ---------------------------------------------------------------------------
from ..agent.financial_agent import financial_agent

@router.get("/financial-agent/batches")
def fa_list_batches():
    return {"batches": financial_agent.list_analysis_batches()}

@router.get("/financial-agent/batch/{batch_id}/assets")
def fa_batch_assets(batch_id: str):
    return {"batch_id": batch_id, "assets": financial_agent.get_batch_assets(batch_id)}

@router.get("/financial-agent/batch/{batch_id}/status")
def fa_batch_status(batch_id: str):
    return financial_agent.get_batch_status(batch_id)

@router.get("/financial-agent/batch/{batch_id}/layer2")
def fa_layer2_stats(batch_id: str):
    return {"batch_id": batch_id, "statistics": financial_agent.get_layer2_statistics(batch_id)}

@router.get("/financial-agent/batch/{batch_id}/layer4")
def fa_layer4_backtests(batch_id: str):
    return {"batch_id": batch_id, "backtests": financial_agent.get_layer4_backtest_results(batch_id)}

# ── Strategy Lab: batch backtest runs with metrics ─────────────────────────
@router.get("/financial-agent/batch/{batch_id}/backtest-runs")
def fa_batch_backtest_runs(batch_id: str):
    """Return all Layer 4 backtest runs for a batch, each with a flat metrics dict."""
    client = financial_agent._ensure_client()
    runs_res = (
        client.table("backtest_runs")
        .select("id, strategy_name, parameters, initial_capital, transaction_cost_rate, slippage_rate, start_date, end_date, status, assets(symbol, name, asset_type)")
        .eq("batch_id", batch_id)
        .execute()
    )
    runs = []
    for r in (runs_res.data or []):
        run_id = r["id"]
        asset_info = r.get("assets") or {}
        metrics_res = (
            client.table("backtest_metrics")
            .select("metric_name, metric_value")
            .eq("backtest_run_id", run_id)
            .execute()
        )
        m = {row["metric_name"]: float(row["metric_value"]) for row in (metrics_res.data or [])}
        runs.append({
            "run_id": run_id,
            "strategy": r.get("strategy_name"),
            "symbol": asset_info.get("symbol", "UNKNOWN"),
            "name": asset_info.get("name", ""),
            "asset_type": asset_info.get("asset_type", ""),
            "parameters": r.get("parameters") or {},
            "initial_capital": r.get("initial_capital"),
            "transaction_cost_rate": r.get("transaction_cost_rate"),
            "slippage_rate": r.get("slippage_rate"),
            "start_date": r.get("start_date"),
            "end_date": r.get("end_date"),
            "status": r.get("status"),
            "metrics": m,
            # convenience top-level fields
            "total_return": m.get("total_return", 0.0),
            "annualized_return": m.get("annualized_return", 0.0),
            "annualized_volatility": m.get("annualized_volatility", 0.0),
            "sharpe_ratio": m.get("sharpe_ratio", 0.0),
            "max_drawdown": m.get("max_drawdown", 0.0),
            "win_rate": m.get("win_rate", 0.0),
            "n_trades": int(m.get("n_trades", 0)),
            "total_transaction_costs": m.get("total_transaction_costs", 0.0),
            "final_portfolio_value": m.get("final_portfolio_value", 0.0),
        })
    return {"batch_id": batch_id, "runs": runs}


# ── Strategy Lab: equity curve for a single backtest run ───────────────────
@router.get("/financial-agent/backtest-run/{run_id}/equity")
def fa_run_equity(run_id: str):
    """Return the daily equity series for a specific backtest run."""
    client = financial_agent._ensure_client()
    # Verify the run exists
    run_res = client.table("backtest_runs").select("id, batch_id, strategy_name, assets(symbol)").eq("id", run_id).execute()
    if not run_res.data:
        raise HTTPException(404, "Backtest run not found")
    run = run_res.data[0]

    eq_res = (
        client.table("backtest_equity")
        .select("date, portfolio_value, daily_return, daily_pnl, position, close_price")
        .eq("backtest_run_id", run_id)
        .order("date")
        .execute()
    )
    rows = eq_res.data or []
    return {
        "run_id": run_id,
        "batch_id": run.get("batch_id"),
        "strategy": run.get("strategy_name"),
        "symbol": (run.get("assets") or {}).get("symbol"),
        "equity": rows,
    }


# ── Strategy Lab: trade log for a single backtest run ─────────────────────
@router.get("/financial-agent/backtest-run/{run_id}/trades")
def fa_run_trades(run_id: str):
    """Return the trade log for a specific backtest run."""
    client = financial_agent._ensure_client()
    run_res = client.table("backtest_runs").select("id, batch_id, strategy_name, assets(symbol)").eq("id", run_id).execute()
    if not run_res.data:
        raise HTTPException(404, "Backtest run not found")
    run = run_res.data[0]

    trades_res = (
        client.table("backtest_trades")
        .select("signal_date, entry_date, entry_price, exit_date, exit_price, units, entry_value, exit_value, entry_transaction_cost, exit_transaction_cost, gross_pnl, net_pnl, return_pct, holding_period_days, status")
        .eq("backtest_run_id", run_id)
        .order("entry_date")
        .execute()
    )
    return {
        "run_id": run_id,
        "batch_id": run.get("batch_id"),
        "strategy": run.get("strategy_name"),
        "symbol": (run.get("assets") or {}).get("symbol"),
        "trades": trades_res.data or [],
    }


@router.get("/financial-agent/batch/{batch_id}/layer5")
def fa_layer5_robustness(batch_id: str):
    return {"batch_id": batch_id, "robustness": financial_agent.get_layer5_robustness_results(batch_id)}

class OptimizationRequest(BaseModel):
    batch_id: str
    capital: float = 100000.0
    objective: str = "MINIMUM_VOLATILITY"
    constraints: Optional[Dict[str, Any]] = None

@router.post("/financial-agent/portfolio")
def fa_run_portfolio(req: OptimizationRequest):
    return financial_agent.run_portfolio_optimization(
        batch_id=req.batch_id,
        capital=req.capital,
        objective=req.objective,
        constraints=req.constraints
    )

@router.post("/financial-agent/qubo")
def fa_run_qubo(req: OptimizationRequest):
    return financial_agent.run_qubo_optimization(
        batch_id=req.batch_id,
        capital=req.capital,
        objective=req.objective,
        constraints=req.constraints
    )

@router.get("/financial-agent/batch/{batch_id}/portfolio-results")
def fa_portfolio_results(batch_id: str):
    return financial_agent.get_portfolio_results(batch_id)


@router.get("/financial-agent/batch/{batch_id}/qubo-results")
def fa_qubo_results(batch_id: str):
    return financial_agent.get_qubo_results(batch_id)


# ---------------------------------------------------------------------------
# Overview Page: Batch-Scoped Consolidated Endpoint
# ---------------------------------------------------------------------------

@router.get("/financial-agent/batch/{batch_id}/overview-data")
def fa_batch_overview_data(batch_id: str):
    """Consolidated Overview endpoint. Never raises 404 - returns partial data gracefully."""
    client = financial_agent._ensure_client()

    # 1. Batch info (graceful)
    batch_info = {"batch_id": batch_id, "batch_name": batch_id,
                  "status": "UNKNOWN", "dataset_filename": "--", "created_at": None}
    try:
        b_res = client.table("analysis_batches").select("*").eq("batch_id", batch_id).execute()
        if b_res.data:
            batch_info = b_res.data[0]
    except Exception as e:
        logger.warning(f"Could not fetch batch_info for {batch_id}: {e}")

    # 2. Batch assets via batch_assets join, with fallback to asset_statistics
    assets_data = financial_agent.get_batch_assets(batch_id)
    if not assets_data:
        try:
            stat_res = (
                client.table("asset_statistics")
                .select("asset_id, assets(id, symbol, name, asset_type)")
                .eq("batch_id", batch_id)
                .execute()
            )
            seen = set()
            for row in (stat_res.data or []):
                a = row.get("assets")
                if a and a.get("symbol") not in seen:
                    seen.add(a.get("symbol"))
                    assets_data.append({
                        "asset_id": a.get("id"),
                        "symbol": a.get("symbol"),
                        "name": a.get("name"),
                        "asset_type": a.get("asset_type"),
                    })
        except Exception as e:
            logger.warning(f"Fallback asset lookup failed for {batch_id}: {e}")

    if not assets_data:
        return {
            "batch_info": batch_info, "assets": [], "statistics": [],
            "latest_prices": {}, "latest_regime": {}, "correlations": [],
            "data_quality": {
                "source": "Supabase", "tracked_assets": 0,
                "batch_status": batch_info.get("status", "UNKNOWN"),
                "dataset_filename": batch_info.get("dataset_filename", "--"),
                "earliest_record": None, "latest_record": None,
                "total_price_records": 0,
            }
        }

    asset_ids = [a["asset_id"] for a in assets_data if a.get("asset_id")]
    symbol_map = {a["asset_id"]: a["symbol"] for a in assets_data}

    # 3. Layer-2 statistics (existing batch-filtered agent method)
    statistics = financial_agent.get_layer2_statistics(batch_id)

    # 4. Latest prices from market_prices per asset
    latest_prices, earliest_dates, latest_dates = {}, {}, {}
    total_records = 0
    if asset_ids:
        try:
            for a_id in asset_ids:
                sym = symbol_map.get(a_id, a_id)
                pr = (client.table("market_prices").select("date, close")
                      .eq("asset_id", a_id).order("date", desc=True).limit(1).execute())
                if pr.data:
                    latest_prices[sym] = {"close": float(pr.data[0]["close"] or 0),
                                          "date": pr.data[0]["date"]}
                    latest_dates[sym] = pr.data[0]["date"]
                pr_f = (client.table("market_prices").select("date")
                        .eq("asset_id", a_id).order("date", desc=False).limit(1).execute())
                if pr_f.data:
                    earliest_dates[sym] = pr_f.data[0]["date"]
                cnt = (client.table("market_prices").select("id", count="exact")
                       .eq("asset_id", a_id).limit(1).execute())
                total_records += (cnt.count or 0)
        except Exception as e:
            logger.warning(f"Price fetch error for {batch_id}: {e}")

    # 5. Latest regime per asset (try with batch_id filter, fall back without)
    latest_regime = {}
    if asset_ids:
        try:
            for a_id in asset_ids:
                sym = symbol_map.get(a_id, a_id)
                reg = None
                try:
                    r = (client.table("market_regimes")
                         .select("regime, trend_state, volatility_state, date")
                         .eq("asset_id", a_id).eq("batch_id", batch_id)
                         .order("date", desc=True).limit(1).execute())
                    if r.data:
                        reg = r.data[0]
                except Exception:
                    pass
                if not reg:
                    try:
                        r2 = (client.table("market_regimes")
                              .select("regime, trend_state, volatility_state, date")
                              .eq("asset_id", a_id).order("date", desc=True).limit(1).execute())
                        if r2.data:
                            reg = r2.data[0]
                    except Exception:
                        pass
                if reg:
                    latest_regime[sym] = {
                        "regime": reg.get("regime", "UNKNOWN"),
                        "trend_state": reg.get("trend_state", "UNKNOWN"),
                        "volatility_state": reg.get("volatility_state", "UNKNOWN"),
                        "date": reg.get("date"),
                    }
        except Exception as e:
            logger.warning(f"Regime fetch error for {batch_id}: {e}")

    # 6. Correlations (90-day window, batch asset pairs only)
    correlations = []
    if len(asset_ids) >= 2:
        try:
            cr = (client.table("asset_correlations")
                  .select("asset_1_id, asset_2_id, correlation, date, window_days")
                  .in_("asset_1_id", asset_ids).in_("asset_2_id", asset_ids)
                  .eq("window_days", 90).order("date", desc=True).limit(100).execute())
            seen_p: set = set()
            for row in (cr.data or []):
                s1 = symbol_map.get(row["asset_1_id"], row["asset_1_id"])
                s2 = symbol_map.get(row["asset_2_id"], row["asset_2_id"])
                p = (s1, s2)
                if p not in seen_p:
                    seen_p.add(p)
                    correlations.append({
                        "asset_1": s1, "asset_2": s2,
                        "correlation": float(row["correlation"] or 0),
                        "window_days": row["window_days"], "date": row["date"],
                    })
        except Exception as e:
            logger.warning(f"Correlation fetch error for {batch_id}: {e}")

    # 7. Data quality summary
    data_quality = {
        "source": "Supabase",
        "earliest_record": min(earliest_dates.values()) if earliest_dates else None,
        "latest_record": max(latest_dates.values()) if latest_dates else None,
        "tracked_assets": len(assets_data),
        "total_price_records": total_records,
        "batch_status": batch_info.get("status", "UNKNOWN"),
        "dataset_filename": batch_info.get("dataset_filename", "--"),
    }

    return {
        "batch_info": batch_info, "assets": assets_data, "statistics": statistics,
        "latest_prices": latest_prices, "latest_regime": latest_regime,
        "correlations": correlations, "data_quality": data_quality,
    }


@router.get("/financial-agent/batch/{batch_id}/prices")
def fa_batch_prices(batch_id: str):
    """Rebased price series for all batch assets. Used for Relative Performance chart."""
    client = financial_agent._ensure_client()
    assets_data = financial_agent.get_batch_assets(batch_id)
    # Fallback via asset_statistics if batch_assets is empty
    if not assets_data:
        try:
            stat_res = (
                client.table("asset_statistics")
                .select("asset_id, assets(id, symbol, name, asset_type)")
                .eq("batch_id", batch_id).execute()
            )
            seen: set = set()
            for row in (stat_res.data or []):
                a = row.get("assets")
                if a and a.get("symbol") not in seen:
                    seen.add(a.get("symbol"))
                    assets_data.append({
                        "asset_id": a.get("id"), "symbol": a.get("symbol"),
                        "name": a.get("name"), "asset_type": a.get("asset_type"),
                    })
        except Exception:
            pass
    if not assets_data:
        return {"batch_id": batch_id, "series": {}}

    symbol_map = {a["asset_id"]: (a["symbol"], a.get("name") or a["symbol"])
                  for a in assets_data}
    series = {}
    for a_id, (sym, name) in symbol_map.items():
        try:
            pr = (client.table("market_prices").select("date, close")
                  .eq("asset_id", a_id).order("date", desc=False).execute())
            rows = pr.data or []
            if not rows:
                continue
            dates = [r["date"] for r in rows]
            closes = [float(r["close"] or 0) for r in rows]
            base = closes[0] if closes[0] != 0 else 1.0
            series[sym] = {
                "name": name, "dates": dates, "closes": closes,
                "rebased": [round((c / base) * 100, 4) for c in closes],
            }
        except Exception as e:
            logger.warning(f"Price series error for {sym} in {batch_id}: {e}")
    return {"batch_id": batch_id, "series": series}


# ---------------------------------------------------------------------------
# Asset Explorer: Batch & Asset Scoped Endpoint
# ---------------------------------------------------------------------------

@router.get("/financial-agent/batch/{batch_id}/asset/{symbol}/explorer")
def fa_batch_asset_explorer(batch_id: str, symbol: str):
    """
    Returns full deep-dive time series and Layer 2 profile metrics for ONE asset
    in the specified batch.
    """
    from ..agent.financial_agent import financial_agent
    client = financial_agent._ensure_client()

    # 1. Resolve batch assets
    assets_data = financial_agent.get_batch_assets(batch_id)
    if not assets_data:
        try:
            stat_res = (
                client.table("asset_statistics")
                .select("asset_id, assets(id, symbol, name, asset_type)")
                .eq("batch_id", batch_id)
                .execute()
            )
            seen = set()
            for row in (stat_res.data or []):
                a = row.get("assets")
                if a and a.get("symbol") not in seen:
                    seen.add(a.get("symbol"))
                    assets_data.append({
                        "asset_id": a.get("id"),
                        "symbol": a.get("symbol"),
                        "name": a.get("name"),
                        "asset_type": a.get("asset_type"),
                    })
        except Exception as e:
            logger.warning(f"Fallback asset lookup failed for {batch_id}: {e}")

    # Find the target asset matching symbol or asset_id (case-insensitive)
    target_asset = None
    for a in assets_data:
        if a.get("symbol", "").upper() == symbol.upper() or a.get("asset_id") == symbol:
            target_asset = a
            break

    if not target_asset:
        raise HTTPException(404, f"Asset '{symbol}' not found in batch '{batch_id}'")

    asset_id = target_asset["asset_id"]
    asset_symbol = target_asset["symbol"]
    asset_name = target_asset.get("name") or asset_symbol
    asset_class = target_asset.get("asset_type") or "Unknown"

    # 2. Fetch Layer 2 metrics from asset_statistics
    stats = {}
    try:
        stat_res = (
            client.table("asset_statistics")
            .select("annualized_return, annualized_volatility, sharpe_ratio, max_drawdown")
            .eq("batch_id", batch_id)
            .eq("asset_id", asset_id)
            .execute()
        )
        if stat_res.data:
            stats = stat_res.data[0]
    except Exception as e:
        logger.warning(f"Error fetching asset_statistics for {asset_symbol} in {batch_id}: {e}")

    # 3. Fetch full historical price data from market_prices (paginated)
    all_rows = []
    offset = 0
    while True:
        try:
            res = (
                client.table("market_prices")
                .select("date, open, high, low, close, volume, source")
                .eq("asset_id", asset_id)
                .order("date", desc=False)
                .range(offset, offset + 999)
                .execute()
            )
            data = res.data or []
            all_rows.extend(data)
            if len(data) < 1000:
                break
            offset += 1000
        except Exception as e:
            logger.warning(f"Error fetching market_prices for {asset_symbol}: {e}")
            break

    if not all_rows:
        raise HTTPException(404, f"No price data available for asset '{asset_symbol}' in batch '{batch_id}'")

    # Deduplicate rows by date
    by_date = {}
    source = "Yahoo Finance"
    for r in all_rows:
        d = r["date"]
        if d not in by_date:
            by_date[d] = r
            if r.get("source"):
                source = r["source"]

    sorted_dates = sorted(by_date.keys())
    opens = [float(by_date[d].get("open") or by_date[d].get("close") or 0.0) for d in sorted_dates]
    highs = [float(by_date[d].get("high") or by_date[d].get("close") or 0.0) for d in sorted_dates]
    lows = [float(by_date[d].get("low") or by_date[d].get("close") or 0.0) for d in sorted_dates]
    closes = [float(by_date[d].get("close") or 0.0) for d in sorted_dates]
    volumes = [float(by_date[d].get("volume") or 0.0) for d in sorted_dates]

    # 4. Compute 20-Day Rolling Returns
    rolling_returns = []
    rolling_dates = []
    if len(closes) > 20:
        rolling_dates = sorted_dates[20:]
        for i in range(20, len(closes)):
            prev_p = closes[i - 20]
            ret = ((closes[i] - prev_p) / prev_p) * 100.0 if prev_p != 0 else 0.0
            rolling_returns.append(round(ret, 4))

    # 5. Compute Running-Peak Historical Drawdowns
    drawdowns = []
    peak = closes[0] if closes else 1.0
    for c in closes:
        if c > peak:
            peak = c
        dd = ((c - peak) / peak) * 100.0 if peak != 0 else 0.0
        drawdowns.append(round(dd, 4))

    # 6. Construct Profile
    last_updated = sorted_dates[-1] if sorted_dates else "-"
    total_observations = len(sorted_dates)

    profile = {
        "name": asset_name,
        "symbol": asset_symbol,
        "asset_class": asset_class,
        "data_source": source,
        "last_updated": last_updated,
        "total_observations": total_observations,
        "annualized_return": float(stats.get("annualized_return") or 0.0),
        "annualized_volatility": float(stats.get("annualized_volatility") or 0.0),
        "sharpe_ratio": float(stats.get("sharpe_ratio") or 0.0),
        "max_drawdown": float(stats.get("max_drawdown") or 0.0),
    }

    return {
        "batch_id": batch_id,
        "symbol": asset_symbol,
        "name": asset_name,
        "asset_class": asset_class,
        "profile": profile,
        "price_volume": {
            "dates": sorted_dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        "rolling_returns": {
            "window_days": 20,
            "label": "20-Day Rolling Return",
            "dates": rolling_dates,
            "returns": rolling_returns,
        },
        "drawdown": {
            "dates": sorted_dates,
            "drawdown": drawdowns,
        },
    }


@router.get("/financial-agent/batch/{batch_id}/correlation-analysis")
def fa_batch_correlation_analysis(batch_id: str, window: str = "full"):
    """
    Correlation & Risk analysis for the selected batch.
    Authoritative Layer 2 / Layer 6 bridge:
    - Only selected batch assets
    - Authoritative correlation values from asset_correlations / portfolio_covariance_inputs
    - Numerical correlation values and covariance matrix
    - Rolling correlation time series (90D) for batch asset pairs
    - Layer 2 risk statistics from asset_statistics
    """
    from collections import defaultdict
    client = financial_agent._ensure_client()

    # 1. Fetch batch info
    batch_info = {
        "batch_id": batch_id,
        "batch_name": batch_id,
        "status": "UNKNOWN",
        "dataset_filename": "--",
        "created_at": None,
    }
    try:
        b_res = client.table("analysis_batches").select("*").eq("batch_id", batch_id).execute()
        if b_res.data:
            batch_info = b_res.data[0]
    except Exception as e:
        logger.warning(f"Could not fetch batch_info for {batch_id}: {e}")

    # 2. Assets in batch
    assets_data = financial_agent.get_batch_assets(batch_id)
    if not assets_data:
        try:
            stat_res = (
                client.table("asset_statistics")
                .select("asset_id, assets(id, symbol, name, asset_type)")
                .eq("batch_id", batch_id)
                .execute()
            )
            seen = set()
            for row in (stat_res.data or []):
                a = row.get("assets")
                if a and a.get("symbol") not in seen:
                    seen.add(a.get("symbol"))
                    assets_data.append({
                        "asset_id": a.get("id"),
                        "symbol": a.get("symbol"),
                        "name": a.get("name"),
                        "asset_type": a.get("asset_type"),
                    })
        except Exception as e:
            logger.warning(f"Fallback asset lookup failed for {batch_id}: {e}")

    # Sort assets canonically: BTC -> GOLD -> NVDA or alphabetical
    def sort_key(a):
        sym = a.get("symbol", "")
        order = {"BTC": 1, "GOLD": 2, "NVDA": 3, "ETH": 4, "AAPL": 5, "TSLA": 6}
        return order.get(sym, 99)

    assets_data.sort(key=sort_key)
    symbols = [a["symbol"] for a in assets_data]
    asset_ids = [a["asset_id"] for a in assets_data]
    id_to_sym = {a["asset_id"]: a["symbol"] for a in assets_data}

    # Minimum 2 assets validation
    if len(symbols) < 2:
        return {
            "batch_id": batch_id,
            "batch_name": batch_info.get("batch_name", batch_id),
            "data_through": None,
            "assets": symbols,
            "matrix": [],
            "window": window,
            "windows_available": ["Full Period", "90D", "60D", "30D"],
            "rolling_series": [],
            "risk_inputs": [],
            "covariance_matrix": [],
            "error": "At least two assets are required for correlation analysis."
        }

    # 3. Data through date
    data_through = None
    try:
        dt_res = (
            client.table("market_prices")
            .select("date")
            .eq("batch_id", batch_id)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        if dt_res.data:
            data_through = dt_res.data[0]["date"]
        elif asset_ids:
            dt_res = (
                client.table("market_prices")
                .select("date")
                .in_("asset_id", asset_ids)
                .order("date", desc=True)
                .limit(1)
                .execute()
            )
            if dt_res.data:
                data_through = dt_res.data[0]["date"]
    except Exception as e:
        logger.warning(f"Error fetching data_through for {batch_id}: {e}")

    # 4. Layer 2 Risk Statistics (asset_statistics)
    risk_inputs = []
    try:
        st_res = client.table("asset_statistics").select("*").eq("batch_id", batch_id).execute()
        st_map = {r["asset_id"]: r for r in (st_res.data or [])}
        for a in assets_data:
            st = st_map.get(a["asset_id"], {})
            risk_inputs.append({
                "symbol": a["symbol"],
                "name": a.get("name", a["symbol"]),
                "asset_type": a.get("asset_type", ""),
                "annualized_volatility": float(st.get("annualized_volatility") or 0.0),
                "sharpe_ratio": float(st.get("sharpe_ratio") or 0.0),
                "max_drawdown": float(st.get("max_drawdown") or 0.0),
                "annualized_return": float(st.get("annualized_return") or 0.0),
            })
    except Exception as e:
        logger.warning(f"Error fetching risk_inputs for {batch_id}: {e}")

    # 5. Layer 6 Covariance & Full Period Correlation (portfolio_covariance_inputs)
    pci_corr = {}
    pci_cov = {}
    try:
        pci_res = client.table("portfolio_covariance_inputs").select("*").eq("batch_id", batch_id).execute()
        if not (pci_res.data or []):
            pci_res = client.table("portfolio_covariance_inputs").select("*").in_("asset_1_symbol", symbols).in_("asset_2_symbol", symbols).execute()
        for r in (pci_res.data or []):
            s1, s2 = r.get("asset_1_symbol"), r.get("asset_2_symbol")
            if s1 and s2:
                if r.get("correlation") is not None:
                    pci_corr[(s1, s2)] = float(r["correlation"])
                if r.get("covariance") is not None:
                    pci_cov[(s1, s2)] = float(r["covariance"])
    except Exception as e:
        logger.warning(f"Error fetching portfolio_covariance_inputs for {batch_id}: {e}")

    # Covariance Matrix
    covariance_matrix = []
    for s1 in symbols:
        row_cov = []
        for s2 in symbols:
            val = pci_cov.get((s1, s2), pci_cov.get((s2, s1), 0.0))
            row_cov.append(round(val, 6))
        covariance_matrix.append(row_cov)

    # 6. Correlation Matrix by Window ("full", "90D", "60D", "30D")
    matrix = []
    window_norm = window.strip().upper() if window else "FULL"
    if window_norm not in ["FULL", "90D", "60D", "30D"]:
        window_norm = "FULL"

    if window_norm == "FULL":
        if pci_corr:
            for s1 in symbols:
                row = []
                for s2 in symbols:
                    if s1 == s2:
                        row.append(1.0)
                    else:
                        val = pci_corr.get((s1, s2), pci_corr.get((s2, s1), 0.0))
                        row.append(round(val, 4))
                matrix.append(row)
        else:
            try:
                mp_res = client.table("market_prices").select("asset_id, date, close").in_("asset_id", asset_ids).execute()
                if mp_res.data:
                    df = pd.DataFrame(mp_res.data)
                    df["symbol"] = df["asset_id"].map(id_to_sym)
                    piv = df.pivot_table(index="date", columns="symbol", values="close").pct_change().dropna()
                    corr_df = piv.corr()
                    for s1 in symbols:
                        row = []
                        for s2 in symbols:
                            row.append(round(float(corr_df.loc[s1, s2]), 4) if s1 in corr_df.index and s2 in corr_df.columns else (1.0 if s1 == s2 else 0.0))
                        matrix.append(row)
            except Exception as e:
                logger.warning(f"Error computing fallback correlation matrix: {e}")
    else:
        w_days = 90 if window_norm == "90D" else (60 if window_norm == "60D" else 30)
        try:
            cr = (
                client.table("asset_correlations")
                .select("asset_1_id, asset_2_id, correlation, date")
                .eq("window_days", w_days)
                .in_("asset_1_id", asset_ids)
                .in_("asset_2_id", asset_ids)
                .order("date", desc=True)
                .limit(200)
                .execute()
            )
            pair_latest = {}
            for r in (cr.data or []):
                s1 = id_to_sym.get(r["asset_1_id"])
                s2 = id_to_sym.get(r["asset_2_id"])
                if not s1 or not s2 or s1 == s2:
                    continue
                p = (s1, s2) if s1 < s2 else (s2, s1)
                if p not in pair_latest:
                    pair_latest[p] = float(r["correlation"])
            for s1 in symbols:
                row = []
                for s2 in symbols:
                    if s1 == s2:
                        row.append(1.0)
                    else:
                        p = (s1, s2) if s1 < s2 else (s2, s1)
                        row.append(round(pair_latest.get(p, 0.0), 4))
                matrix.append(row)
        except Exception as e:
            logger.warning(f"Error fetching rolling matrix for window {w_days}: {e}")

    # Fallback if matrix is empty
    if not matrix or len(matrix) != len(symbols):
        matrix = [[1.0 if i == j else 0.0 for j in range(len(symbols))] for i in range(len(symbols))]

    # 7. Rolling Correlation Time Series (90-Day window for all batch pairs)
    rolling_series = []
    try:
        all_corr_rows = []
        offset = 0
        while True:
            res = (
                client.table("asset_correlations")
                .select("asset_1_id, asset_2_id, correlation, date")
                .eq("batch_id", batch_id)
                .eq("window_days", 90)
                .order("date")
                .range(offset, offset + 999)
                .execute()
            )
            batch = res.data or []
            if not batch and offset == 0:
                # Fallback if correlations were stored without batch_id tag
                res = (
                    client.table("asset_correlations")
                    .select("asset_1_id, asset_2_id, correlation, date")
                    .eq("window_days", 90)
                    .in_("asset_1_id", asset_ids)
                    .in_("asset_2_id", asset_ids)
                    .order("date")
                    .range(offset, offset + 999)
                    .execute()
                )
                batch = res.data or []
            all_corr_rows.extend(batch)
            if len(batch) < 1000 or offset >= 10000:
                break
            offset += 1000

        # Group by pair
        series_by_pair = defaultdict(dict)
        for r in all_corr_rows:
            if data_through and r.get("date") and r["date"] > data_through:
                continue
            s1 = id_to_sym.get(r["asset_1_id"])
            s2 = id_to_sym.get(r["asset_2_id"])
            if not s1 or not s2 or s1 == s2:
                continue
            pair_key = (s1, s2) if s1 < s2 else (s2, s1)
            pair_name = f"{pair_key[0]} ↔ {pair_key[1]}"
            series_by_pair[pair_name][r["date"]] = float(r["correlation"])

        # Format series time-ordered
        for pair_name, date_dict in sorted(series_by_pair.items()):
            sorted_dates = sorted(date_dict.keys())
            sorted_corrs = [round(date_dict[d], 4) for d in sorted_dates]
            parts = pair_name.split(" ↔ ")
            rolling_series.append({
                "pair": pair_name,
                "asset_1": parts[0],
                "asset_2": parts[1],
                "window_days": 90,
                "dates": sorted_dates,
                "correlations": sorted_corrs,
                "latest_correlation": sorted_corrs[-1] if sorted_corrs else None,
            })
    except Exception as e:
        logger.warning(f"Error fetching rolling correlation series for {batch_id}: {e}")

    return {
        "batch_id": batch_id,
        "batch_name": batch_info.get("batch_name", batch_id),
        "data_through": data_through,
        "assets": symbols,
        "matrix": matrix,
        "window": "Full Period" if window_norm == "FULL" else window_norm,
        "windows_available": ["Full Period", "90D", "60D", "30D"],
        "rolling_series": rolling_series,
        "risk_inputs": risk_inputs,
        "covariance_matrix": covariance_matrix,
    }


