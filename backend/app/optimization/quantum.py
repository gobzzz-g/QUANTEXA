import numpy as np
import pandas as pd
from typing import Dict

def optimize_portfolio_qubo(expected_returns: pd.Series, cov_matrix: pd.DataFrame, risk_aversion: float = 0.5, num_assets_limit: int = None) -> Dict:
    """
    Formulates a Quadratic Unconstrained Binary Optimization (QUBO) problem
    for portfolio selection and provides a classical baseline simulated result.
    
    In a true quantum implementation (e.g. D-Wave), this QUBO would be passed
    to a QPU or hybrid solver.
    """
    assets = expected_returns.index.tolist()
    num_assets = len(assets)
    
    # 1. QUBO Formulation
    # Maximize Returns - RiskAversion * Variance
    # We map this to a binary problem where x_i in {0, 1} indicates asset inclusion
    
    # Linear terms (diagonal of Q matrix) related to expected returns
    # We negate because QUBO solvers typically minimize
    Q_linear = -np.diag(expected_returns.values)
    
    # Quadratic terms (off-diagonal) related to risk/covariance
    Q_quad = risk_aversion * cov_matrix.values
    
    Q = Q_linear + Q_quad
    
    # In a real quantum implementation, Q would be sent to the solver.
    # Here, we will perform a classical brute-force for demonstration 
    # (only feasible for small N, which is typical for demo portfolios).
    
    best_cost = float('inf')
    best_x = None
    
    # Brute force search space 2^N (only for very small N in this demo)
    # If N is large, we should use simulated annealing, but N is ~4 for our seed data.
    if num_assets <= 15:
        import itertools
        for x in itertools.product([0, 1], repeat=num_assets):
            x_vec = np.array(x)
            if np.sum(x_vec) == 0:
                continue
            
            if num_assets_limit and np.sum(x_vec) > num_assets_limit:
                continue
                
            cost = np.dot(x_vec.T, np.dot(Q, x_vec))
            if cost < best_cost:
                best_cost = cost
                best_x = x_vec
    else:
        # Fallback heuristic for larger N (pick top 3 returns)
        best_x = np.zeros(num_assets)
        top_idx = np.argsort(expected_returns.values)[-3:]
        best_x[top_idx] = 1
        
    # Convert binary selection back to continuous equal weights among selected
    selected_assets_count = np.sum(best_x)
    weights = best_x / selected_assets_count if selected_assets_count > 0 else np.zeros(num_assets)
    
    # Calculate performance of this selection
    port_return = np.sum(expected_returns.values * weights)
    port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix.values, weights)))
    sharpe = port_return / port_vol if port_vol > 0 else 0.0
    
    return {
        "method": "qubo_simulated",
        "weights": {asset: float(weight) for asset, weight in zip(assets, weights)},
        "expected_return": float(port_return),
        "volatility": float(port_vol),
        "sharpe_ratio": float(sharpe),
        "qubo_cost": float(best_cost)
    }
