from typing import Dict, Any, List
import pandas as pd
from ..strategies.base import SMACrossover, EMATrend, Momentum, MeanReversion
from ..backtest.engine import BacktestEngine
from ..config import settings

def run_parameter_grid(df: pd.DataFrame, asset: str, strategy_name: str) -> List[Dict[str, Any]]:
    ann_factor = settings.assets[asset].calendar_days
    
    results = []
    
    grids = {
        "sma_crossover": [{"fast": 10, "slow": 30}, {"fast": 20, "slow": 50}, {"fast": 50, "slow": 200}],
        "ema_trend": [{"fast": 8, "slow": 21}, {"fast": 12, "slow": 26}, {"fast": 20, "slow": 50}],
        "momentum": [{"lookback": 30, "threshold": 0.0}, {"lookback": 90, "threshold": 0.0}, {"lookback": 180, "threshold": 0.0}],
        "mean_reversion": [{"lookback": 20, "z_enter": -2.0, "z_exit": 0.0}, {"lookback": 20, "z_enter": -1.5, "z_exit": 0.5}]
    }
    
    if strategy_name not in grids:
        return []
        
    for params in grids[strategy_name]:
        if strategy_name == "sma_crossover":
            strat = SMACrossover(params['fast'], params['slow'])
        elif strategy_name == "ema_trend":
            strat = EMATrend(params['fast'], params['slow'])
        elif strategy_name == "momentum":
            strat = Momentum(params['lookback'], params['threshold'])
        elif strategy_name == "mean_reversion":
            strat = MeanReversion(params['lookback'], params['z_enter'], params['z_exit'])
            
        signal = strat.generate_positions(df)
        engine = BacktestEngine(df, signal, ann_factor)
        res = engine.run()
        
        results.append({
            "params": params,
            "cagr": res["strategy"]["cagr"],
            "sharpe": res["strategy"]["sharpe"],
            "max_drawdown": res["strategy"]["max_drawdown"]
        })
        
    return results
