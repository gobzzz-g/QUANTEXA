import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import List, Dict, Tuple

def get_portfolio_stats(weights: np.ndarray, expected_returns: np.ndarray, cov_matrix: np.ndarray, risk_free_rate: float = 0.0) -> Tuple[float, float, float]:
    """
    Calculate annualized return, volatility, and Sharpe ratio for a given weight vector.
    """
    port_return = np.sum(expected_returns * weights)
    port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
    sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 0 else 0.0
    return port_return, port_vol, sharpe

def optimize_portfolio(expected_returns: pd.Series, cov_matrix: pd.DataFrame, method: str = 'max_sharpe', risk_free_rate: float = 0.0) -> Dict:
    """
    Optimize portfolio weights based on the specified method.
    Methods: 'equal_weight', 'min_volatility', 'max_sharpe'
    """
    num_assets = len(expected_returns)
    assets = expected_returns.index.tolist()
    
    if method == 'equal_weight':
        weights = np.array([1.0 / num_assets] * num_assets)
        port_return, port_vol, sharpe = get_portfolio_stats(weights, expected_returns.values, cov_matrix.values, risk_free_rate)
        return {
            "method": method,
            "weights": {asset: float(weight) for asset, weight in zip(assets, weights)},
            "expected_return": float(port_return),
            "volatility": float(port_vol),
            "sharpe_ratio": float(sharpe)
        }

    # Common constraints and bounds
    # Weights sum to 1
    constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
    # Long only (weights between 0 and 1)
    bounds = tuple((0, 1) for _ in range(num_assets))
    
    # Initial guess: equal weight
    initial_guess = np.array([1.0 / num_assets] * num_assets)
    
    if method == 'min_volatility':
        # Objective: minimize variance
        def obj_min_vol(weights, cov_matrix):
            return np.dot(weights.T, np.dot(cov_matrix, weights))
            
        result = minimize(obj_min_vol, initial_guess, args=(cov_matrix.values,), method='SLSQP', bounds=bounds, constraints=constraints)
    
    elif method == 'max_sharpe':
        # Objective: minimize negative Sharpe
        def obj_max_sharpe(weights, expected_returns, cov_matrix, risk_free_rate):
            port_return = np.sum(expected_returns * weights)
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            if port_vol == 0:
                return 0
            return -(port_return - risk_free_rate) / port_vol
            
        result = minimize(obj_max_sharpe, initial_guess, args=(expected_returns.values, cov_matrix.values, risk_free_rate), method='SLSQP', bounds=bounds, constraints=constraints)
    
    else:
        raise ValueError(f"Unknown optimization method: {method}")
        
    if not result.success:
        # Fallback to equal weight if optimization fails
        return optimize_portfolio(expected_returns, cov_matrix, 'equal_weight', risk_free_rate)
        
    optimized_weights = result.x
    port_return, port_vol, sharpe = get_portfolio_stats(optimized_weights, expected_returns.values, cov_matrix.values, risk_free_rate)
    
    return {
        "method": method,
        "weights": {asset: float(weight) for asset, weight in zip(assets, optimized_weights)},
        "expected_return": float(port_return),
        "volatility": float(port_vol),
        "sharpe_ratio": float(sharpe)
    }
