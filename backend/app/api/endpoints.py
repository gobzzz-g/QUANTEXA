from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
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

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/assets")
def get_assets():
    return get_all_assets()

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
def get_robustness(asset: str, strategy: str):
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

@router.get("/correlation")
def get_correlation():
    dfs = {}
    assets = get_all_assets()
    for asset in assets:
        try:
            _, df = _get_provenance(asset, assets)
            if not df.empty:
                dfs[asset] = df
        except Exception:
            pass # Skip missing data
            
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
    assets: List[str] = None

from ..agent.research import run_research_query

import pandas as pd

@router.get("/market-analysis")
def get_market_analysis(lookback: str = "1Y"):
    assets = get_all_assets()
    
    dfs = {}
    latest_date = None
    
    for asset in assets:
        try:
            prov, df = _get_provenance(asset, assets)
            if not df.empty:
                dfs[asset] = df
                d = df.index[-1]
                if latest_date is None or d > latest_date:
                    latest_date = d
        except Exception:
            pass
            
    if not dfs:
        raise HTTPException(404, "No historical data available")
        
    # Apply lookback filter
    cutoff_date = None
    if latest_date and lookback != "MAX":
        if lookback == "1M":
            cutoff_date = latest_date - pd.DateOffset(months=1)
        elif lookback == "3M":
            cutoff_date = latest_date - pd.DateOffset(months=3)
        elif lookback == "6M":
            cutoff_date = latest_date - pd.DateOffset(months=6)
        elif lookback == "1Y":
            cutoff_date = latest_date - pd.DateOffset(years=1)
            
    filtered_dfs = {}
    for k, df in dfs.items():
        if cutoff_date:
            f_df = df[df.index >= cutoff_date]
            if not f_df.empty:
                filtered_dfs[k] = f_df
        else:
            filtered_dfs[k] = df
            
    if not filtered_dfs:
        raise HTTPException(404, "No data available for the selected period")
        
    # 1. Chart Data
    chart_data = {}
    for k, df in filtered_dfs.items():
        rebased = (df['Close'] / df['Close'].iloc[0] * 100).tolist()
        chart_data[k] = {
            "dates": df.index.strftime("%Y-%m-%d").tolist(),
            "rebased": rebased
        }
        
    # 2. Asset Monitor & Breadth
    advancing = 0
    declining = 0
    unchanged = 0
    monitor = []
    
    for k, df in filtered_dfs.items():
        if len(df) >= 2:
            start_price = float(df['Close'].iloc[0])
            end_price = float(df['Close'].iloc[-1])
            prev_price = float(df['Close'].iloc[-2])
            
            period_return = (end_price - start_price) / start_price if start_price != 0 else 0
            daily_return = (end_price - prev_price) / prev_price if prev_price != 0 else 0
            
            if period_return > 0.001:
                advancing += 1
            elif period_return < -0.001:
                declining += 1
            else:
                unchanged += 1
                
            rets = df['Close'].pct_change().dropna()
            N = assets[k]["calendar_days"]
            vol = calc_annualized_volatility(rets, N)
            
            monitor.append({
                "symbol": k,
                "name": assets[k]["name"],
                "asset_class": assets[k].get("asset_class", "Unknown"),
                "current_price": end_price,
                "daily_return": daily_return,
                "period_return": period_return,
                "volatility": vol
            })
            
    # 3. Sector Performance
    sectors = {}
    for m in monitor:
        cls = m["asset_class"]
        if cls not in sectors:
            sectors[cls] = []
        sectors[cls].append(m["period_return"])
        
    sector_perf = {}
    for cls, rets in sectors.items():
        sector_perf[cls] = sum(rets) / len(rets)
        
    # 4. KPIs
    returns = [m["period_return"] for m in monitor]
    vols = [m["volatility"] for m in monitor]
    
    avg_return = sum(returns) / len(returns) if returns else 0
    avg_vol = sum(vols) / len(vols) if vols else 0
    best_perf = max(monitor, key=lambda x: x["period_return"]) if monitor else None
    worst_perf = min(monitor, key=lambda x: x["period_return"]) if monitor else None
    
    return {
        "chart_data": chart_data,
        "breadth": {
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "total": advancing + declining + unchanged
        },
        "monitor": monitor,
        "sector_performance": sector_perf,
        "kpis": {
            "tracked_assets": len(assets),
            "avg_return": avg_return,
            "avg_volatility": avg_vol,
            "best_performer": best_perf["name"] if best_perf else "-",
            "worst_performer": worst_perf["name"] if worst_perf else "-",
            "data_through": latest_date.strftime("%Y-%m-%d") if latest_date else "-"
        }
    }

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
