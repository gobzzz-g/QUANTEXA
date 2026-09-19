from typing import Dict, List, Any
import logging
from ..data.supabase_client import supabase

logger = logging.getLogger(__name__)

_GRAPH_CACHE = None

def build_dynamic_graph() -> Dict[str, Any]:
    global _GRAPH_CACHE
    if _GRAPH_CACHE:
        return _GRAPH_CACHE
        
    if not supabase:
        logger.warning("Supabase client not initialized, returning empty graph")
        return {"nodes": [], "links": []}

    nodes = []
    edges = []
    entities_added = set()

    def add_node(id_str: str, name: str, n_type: str, props: dict = None):
        if id_str and id_str not in entities_added:
            nodes.append({
                "id": str(id_str),
                "name": str(name),
                "type": n_type,
                **(props or {})
            })
            entities_added.add(id_str)
            
    def add_edge(source: str, target: str, e_type: str, props: dict = None):
        source_str = str(source)
        target_str = str(target)
        if source_str and target_str and source_str in entities_added and target_str in entities_added:
            # check if edge exists
            exists = any(e for e in edges if e["source"] == source_str and e["target"] == target_str and e["type"] == e_type)
            if not exists:
                edges.append({
                    "source": source_str,
                    "target": target_str,
                    "type": e_type,
                    **(props or {})
                })

    try:
        # Fetch data in bulk
        assets_res = supabase.table('assets').select('*').execute()
        assets = assets_res.data or []
        
        correlations_res = supabase.table('asset_correlations').select('*').execute()
        correlations = correlations_res.data or []
        
        # for market regimes, we only need unique asset/regime pairs or just unique regimes
        regimes_res = supabase.table('market_regimes').select('asset_id, regime').execute()
        regimes = regimes_res.data or []
        
        backtests_res = supabase.table('backtest_runs').select('id, asset_id, strategy_name').execute()
        backtests = backtests_res.data or []
        
        robustness_res = supabase.table('robustness_results').select('id, asset_id, strategy_name').execute()
        robustness = robustness_res.data or []
        
        portfolios_res = supabase.table('portfolio_optimization_runs').select('id, objective').execute()
        portfolios = portfolios_res.data or []
        
        qubos_res = supabase.table('qubo_runs').select('id, portfolio_run_id').execute()
        qubos = qubos_res.data or []

        # 1. Assets
        asset_id_map = {}
        for a in assets:
            a_id = str(a['id'])
            asset_id_map[a_id] = a
            name = a.get('name') or a.get('symbol') or a.get('source_dataset')
            add_node(a_id, name, "Asset")
            
        # 2. Strategies (implied from backtests and robustness)
        strategy_names = set([b['strategy_name'] for b in backtests if b.get('strategy_name')] + [r['strategy_name'] for r in robustness if r.get('strategy_name')])
        for s in strategy_names:
            add_node(f"Strategy_{s}", s, "Strategy")
            
        # 3. Market Regimes (unique regime labels)
        unique_regimes = set([r['regime'] for r in regimes if r.get('regime')])
        for r in unique_regimes:
            add_node(f"Regime_{r}", r, "Market Regime")
            
        # 4. Backtests
        for b in backtests:
            b_id = str(b['id'])
            add_node(b_id, f"Backtest: {b.get('strategy_name', 'Unknown')}", "Backtest")
            
        # 5. Robustness
        for r in robustness:
            r_id = str(r['id'])
            add_node(r_id, f"Robustness: {r.get('strategy_name', 'Unknown')}", "Robustness")
            
        # 6. Portfolios
        for p in portfolios:
            p_id = str(p['id'])
            obj = p.get('objective', 'Unknown Objective')
            add_node(p_id, f"Portfolio: {obj}", "Portfolio")
            
        # 7. QUBO
        for q in qubos:
            q_id = str(q['id'])
            add_node(q_id, f"QUBO Run", "QUBO")
            
        # --- Edges ---
        
        # Correlations (Assets -> Assets)
        for c in correlations:
            a1 = str(c.get('asset_1_id'))
            a2 = str(c.get('asset_2_id'))
            val = c.get('correlation')
            # Only connect strong correlations to prevent visual soup
            if val is not None and abs(val) > 0.5:
                edge_type = "CORRELATED_WITH" if val > 0 else "INVERSE_CORRELATED_WITH"
                add_edge(a1, a2, edge_type, {"correlation": val, "window": c.get('window_days')})
                
        # Regimes (Asset -> Regime)
        # To avoid duplicating edges, track connected regimes per asset
        asset_regime_links = set()
        for r in regimes:
            a_id = str(r.get('asset_id'))
            reg = r.get('regime')
            if a_id and reg:
                link_key = f"{a_id}_{reg}"
                if link_key not in asset_regime_links:
                    add_edge(a_id, f"Regime_{reg}", "EXPERIENCES_REGIME")
                    asset_regime_links.add(link_key)
                    
        # Backtests (Asset -> Backtest, Backtest -> Strategy)
        for b in backtests:
            b_id = str(b['id'])
            a_id = str(b.get('asset_id'))
            s_name = b.get('strategy_name')
            if a_id:
                add_edge(a_id, b_id, "HAS_BACKTEST")
            if s_name:
                add_edge(b_id, f"Strategy_{s_name}", "TESTS_STRATEGY")
                if a_id: # Asset -> Strategy connection through backtest
                    add_edge(a_id, f"Strategy_{s_name}", "USES_STRATEGY")
                    
        # Robustness (Asset -> Robustness, Robustness -> Strategy)
        for r in robustness:
            r_id = str(r['id'])
            a_id = str(r.get('asset_id'))
            s_name = r.get('strategy_name')
            if a_id:
                add_edge(a_id, r_id, "HAS_ROBUSTNESS_TEST")
            if s_name:
                add_edge(r_id, f"Strategy_{s_name}", "TESTS_STRATEGY")
                
        # QUBO (Portfolio -> QUBO)
        for q in qubos:
            q_id = str(q['id'])
            p_id = str(q.get('portfolio_run_id'))
            if p_id:
                add_edge(p_id, q_id, "OPTIMIZED_BY_QUBO")

    except Exception as e:
        logger.error(f"Error building graph: {e}")

    _GRAPH_CACHE = {
        "nodes": nodes,
        "links": edges
    }
    return _GRAPH_CACHE

def get_full_graph() -> Dict[str, Any]:
    return build_dynamic_graph()

def get_entity_context(entity_id: str) -> Dict[str, Any]:
    graph = build_dynamic_graph()
    nodes = graph["nodes"]
    edges = graph["links"]
    
    node = next((n for n in nodes if n["id"] == entity_id), None)
    if not node:
        return {}
        
    related_links = [l for l in edges if l["source"] == entity_id or l["target"] == entity_id]
    related_nodes_ids = set()
    for l in related_links:
        related_nodes_ids.add(l["source"])
        related_nodes_ids.add(l["target"])
        
    related_nodes = [n for n in nodes if n["id"] in related_nodes_ids]
    
    # Query rich context based on type
    metrics = {}
    description = ""
    
    if not supabase:
        return {"entity": node, "relationships": related_links, "related_entities": related_nodes}
        
    try:
        if node["type"] == "Asset":
            res = supabase.table('asset_statistics').select('*').eq('asset_id', entity_id).order('created_at', desc=True).limit(1).execute()
            if res.data:
                stat = res.data[0]
                metrics = {
                    "Annualized Return (CAGR)": f"{stat.get('annualized_return', 0)*100:.2f}%",
                    "Annualized Volatility": f"{stat.get('annualized_volatility', 0)*100:.2f}%",
                    "Sharpe Ratio": f"{stat.get('sharpe_ratio', 0):.2f}",
                    "Max Drawdown": f"{stat.get('max_drawdown', 0)*100:.2f}%"
                }
            # fetch current price
            prices_res = supabase.table('market_prices').select('close, date').eq('asset_id', entity_id).order('date', desc=True).limit(1).execute()
            if prices_res.data:
                metrics["Latest Price"] = f"${prices_res.data[0].get('close'):.2f}"
                description = f"Last updated: {prices_res.data[0].get('date')}"
                
        elif node["type"] == "Backtest":
            res = supabase.table('backtest_runs').select('*').eq('id', entity_id).execute()
            if res.data:
                run = res.data[0]
                metrics = {
                    "Status": run.get('status'),
                    "Initial Capital": f"${run.get('initial_capital', 0):,.2f}",
                    "Start Date": run.get('start_date'),
                    "End Date": run.get('end_date')
                }
                if run.get('parameters'):
                    description = f"Params: {run.get('parameters')}"
                    
        elif node["type"] == "Portfolio":
            res = supabase.table('portfolio_optimization_runs').select('*').eq('id', entity_id).execute()
            if res.data:
                run = res.data[0]
                metrics = {
                    "Objective": run.get('objective'),
                    "Target Return": run.get('target_return'),
                    "Status": run.get('status')
                }
                
        elif node["type"] == "Robustness":
            res = supabase.table('robustness_results').select('*').eq('id', entity_id).execute()
            if res.data:
                run = res.data[0]
                metrics = {
                    "Test Type": run.get('test_type'),
                    "Test Value": run.get('test_value'),
                    "Win Rate": f"{run.get('win_rate', 0)*100:.2f}%",
                    "Sharpe Ratio": f"{run.get('sharpe_ratio', 0):.2f}"
                }
                
        elif node["type"] == "QUBO":
            res = supabase.table('qubo_runs').select('*').eq('id', entity_id).execute()
            if res.data:
                run = res.data[0]
                metrics = {
                    "Risk Weight": run.get('risk_weight'),
                    "Return Weight": run.get('return_weight'),
                    "Constraint Penalty": run.get('constraint_penalty'),
                    "Variables": run.get('num_binary_variables'),
                    "Status": run.get('status')
                }
    except Exception as e:
        logger.error(f"Error fetching context for {entity_id}: {e}")

    node_copy = dict(node)
    node_copy["metrics"] = metrics
    if description:
        node_copy["description"] = description
    
    return {
        "entity": node_copy,
        "relationships": related_links,
        "related_entities": related_nodes
    }
