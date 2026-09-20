"""
kg_pipeline_bridge.py — Knowledge Graph & OpenClaw Integration for 7-Layer Pipeline
===================================================================================
Connects the 7-Layer Quantitative Multi-Asset Financial Intelligence Pipeline to the
Neo4j Knowledge Graph (OpenClaw-KG) and links batch results into graph ontology:

1. Canonical Pipeline & Layer Ontology:
   (:Platform {name: 'QuantExa'})-[:HOSTS_PIPELINE]->(:ExecutionPipeline {name: '7-Layer Quantitative Pipeline'})
   - Layer 1: Data Ingestion (ingest.py -> market_prices, assets)
   - Layer 2: Quant Engine (quant_engine.py -> asset_indicators, asset_statistics, asset_correlations)
   - Layer 3: Strategy Engine (strategy_engine.py -> strategy_signals)
   - Layer 4: Backtesting Engine (backtest_engine.py -> backtest_runs, backtest_equity, backtest_trades, backtest_metrics)
   - Layer 5: Robustness Engine (robustness_engine.py -> market_regimes, robustness_results)
   - Layer 6: Portfolio Optimizer (portfolio_optimizer.py -> portfolio_allocations, portfolio_results)
   - Layer 7: QUBO Solver (qubo_optimizer.py -> qubo_runs, qubo_variables, qubo_matrix, qubo_results)

2. Direct Batch Data Lineage:
   Syncs batch metrics (TEST_BATCH_01, etc.) from Supabase into Neo4j nodes and relationships:
   - AnalysisBatch, Asset, Strategy, MarketRegime, PortfolioAllocation, QUBOSolver
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

# Load pipeline environment
PIPELINE_DIR = Path(__file__).resolve().parent
load_dotenv(PIPELINE_DIR / ".env")

# IPv4 first patch for Neo4j and Supabase on Windows
import socket as _socket
_orig_gai = _socket.getaddrinfo
def _ipv4_first(h, p, f=0, t=0, pr=0, fl=0):
    r = _orig_gai(h, p, f, t, pr, fl)
    return sorted(r, key=lambda x: 0 if x[0] == _socket.AF_INET else 1)
_socket.getaddrinfo = _ipv4_first

from neo4j import GraphDatabase, basic_auth

NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j+s://e2a2d5d2.databases.neo4j.io")
NEO4J_USER = os.environ.get("NEO4J_USERNAME", "e2a2d5d2")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "FJ7aLodKEhcOr2WafoWi-XiVmBvyhuFGTipKQxfEcNQ")

def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

def get_supabase_client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    return create_client(url, key)


PIPELINE_LAYERS = [
    {
        "layer_num": 1,
        "name": "Data Ingestion",
        "script": "ingest.py",
        "description": "Loads raw multi-asset OHLCV market data, validates quality, enforces asset taxonomy, and tags batch isolation.",
        "tables": ["market_prices", "assets", "ingestion_runs"]
    },
    {
        "layer_num": 2,
        "name": "Quantitative Engine",
        "script": "quant_engine.py",
        "description": "Computes rolling indicators (SMA, EMA, Volatility, Sharpe) and full-period statistical covariance and correlations.",
        "tables": ["asset_indicators", "asset_statistics", "asset_correlations"]
    },
    {
        "layer_num": 3,
        "name": "Strategy Engine",
        "script": "strategy_engine.py",
        "description": "Generates discrete trading signals (LONG, FLAT, EXIT) across SMA Crossover, EMA Trend, Momentum, and Mean Reversion.",
        "tables": ["strategy_signals"]
    },
    {
        "layer_num": 4,
        "name": "Backtesting Engine",
        "script": "backtest_engine.py",
        "description": "Simulates historical execution with next-day open fills, 0.1% transaction friction, generating equity curves and performance metrics.",
        "tables": ["backtest_runs", "backtest_equity", "backtest_trades", "backtest_metrics", "benchmark_results"]
    },
    {
        "layer_num": 5,
        "name": "Robustness & Regimes",
        "script": "robustness_engine.py",
        "description": "Evaluates parameter sweeps, transaction fee sensitivity, and classifies 5 market regimes (Bull/Bear x Volatility).",
        "tables": ["market_regimes", "robustness_results", "strategy_regime_performance"]
    },
    {
        "layer_num": 6,
        "name": "Portfolio Optimization",
        "script": "portfolio_optimizer.py",
        "description": "Solves classical Markowitz mean-variance optimization (Min Vol, Max Sharpe, Target Return) and discretizes allocations.",
        "tables": ["portfolio_optimization_runs", "portfolio_allocations", "portfolio_results", "portfolio_covariance_inputs"]
    },
    {
        "layer_num": 7,
        "name": "QUBO Optimization",
        "script": "qubo_optimizer.py",
        "description": "Encodes portfolio allocation as Quadratic Unconstrained Binary Optimization solved via Classical Exact and Quantum-Inspired Simulated Annealing.",
        "tables": ["qubo_runs", "qubo_variables", "qubo_matrix", "qubo_results"]
    }
]


def sync_pipeline_ontology(session) -> None:
    """Sync the canonical 7-Layer Pipeline architecture into Neo4j."""
    print("  Syncing canonical 7-Layer Pipeline structure into Neo4j...")
    pipeline_query = """
        MERGE (p:Platform {name: 'QuantExa'})
        SET p.description = 'Enterprise Quantitative Multi-Asset Financial Intelligence Terminal'
        MERGE (pipe:ExecutionPipeline {name: 'QuantitativeMultiAssetPipeline'})
        SET pipe.title = '7-Layer Quantitative Multi-Asset Pipeline',
            pipe.layers_count = 7,
            pipe.batch_isolated = true,
            pipe.updated_at = datetime()
        MERGE (p)-[:HOSTS_PIPELINE]->(pipe)
    """
    session.run(pipeline_query)

    for layer in PIPELINE_LAYERS:
        layer_query = """
            MATCH (pipe:ExecutionPipeline {name: 'QuantitativeMultiAssetPipeline'})
            MERGE (l:PipelineLayer {layer_number: $layer_num})
            SET l.name = $name,
                l.script = $script,
                l.description = $description,
                l.output_tables = $tables,
                l.updated_at = datetime()
            MERGE (pipe)-[:CONTAINS_LAYER {order: $layer_num}]->(l)
        """
        session.run(layer_query, {
            "layer_num": layer["layer_num"],
            "name": layer["name"],
            "script": layer["script"],
            "description": layer["description"],
            "tables": layer["tables"]
        })

    # Link layer sequence: (L1)-[:FEEDS_INTO]->(L2)-[:FEEDS_INTO]->...->(L7)
    for i in range(1, 7):
        seq_query = """
            MATCH (l1:PipelineLayer {layer_number: $l1_num})
            MATCH (l2:PipelineLayer {layer_number: $l2_num})
            MERGE (l1)-[:FEEDS_INTO]->(l2)
        """
        session.run(seq_query, {"l1_num": i, "l2_num": i + 1})


def sync_batch_to_neo4j(batch_id: str) -> Dict[str, Any]:
    """Extract batch data from Supabase across all 7 layers and project it into Neo4j."""
    print(f"\n==================================================")
    print(f"KNOWLEDGE GRAPH SYNC: {batch_id}")
    print(f"==================================================")

    client = get_supabase_client()
    driver = get_neo4j_driver()

    sync_summary = {
        "batch_id": batch_id,
        "layers_synced": [],
        "nodes_created": 0,
        "relationships_created": 0
    }

    try:
        with driver.session() as session:
            # 1. Base ontology
            sync_pipeline_ontology(session)

            # 2. Batch node
            batch_data = client.table("analysis_batches").select("*").eq("batch_id", batch_id).execute().data
            b_status = batch_data[0].get("status", "COMPLETED") if batch_data else "COMPLETED"
            created_at = batch_data[0].get("created_at") if batch_data else datetime.now(timezone.utc).isoformat()

            session.run("""
                MATCH (pipe:ExecutionPipeline {name: 'QuantitativeMultiAssetPipeline'})
                MERGE (b:AnalysisBatch {batch_id: $batch_id})
                SET b.status = $status,
                    b.created_at = $created_at,
                    b.synced_at = datetime()
                MERGE (b)-[:PROCESSED_BY_PIPELINE]->(pipe)
            """, {"batch_id": batch_id, "status": b_status, "created_at": created_at})
            sync_summary["layers_synced"].append("Batch Node")

            # 3. Layer 1 & 2: Assets & Statistics
            stats = client.table("asset_statistics").select("*, assets(symbol, asset_type)").eq("batch_id", batch_id).execute().data
            for row in stats:
                sym = row.get("assets", {}).get("symbol") if row.get("assets") else "UNKNOWN"
                asset_type = row.get("assets", {}).get("asset_type", "EQUITY")
                ann_ret = float(row.get("annualized_return", 0.0))
                ann_vol = float(row.get("annualized_volatility", 0.0))
                sharpe = float(row.get("sharpe_ratio", 0.0))
                max_dd = float(row.get("max_drawdown", 0.0))

                session.run("""
                    MATCH (b:AnalysisBatch {batch_id: $batch_id})
                    MATCH (l2:PipelineLayer {layer_number: 2})
                    MERGE (a:Asset {symbol: $symbol})
                    SET a.asset_type = $asset_type
                    MERGE (b)-[:CONTAINS_ASSET]->(a)
                    MERGE (b)-[r:EVALUATED_METRIC {batch_id: $batch_id}]->(a)
                    SET r.annualized_return = $ann_ret,
                        r.annualized_volatility = $ann_vol,
                        r.sharpe_ratio = $sharpe,
                        r.max_drawdown = $max_dd,
                        r.updated_at = datetime()
                    MERGE (l2)-[:COMPUTED_STATISTICS]->(a)
                """, {
                    "batch_id": batch_id,
                    "symbol": sym,
                    "asset_type": asset_type,
                    "ann_ret": ann_ret,
                    "ann_vol": ann_vol,
                    "sharpe": sharpe,
                    "max_dd": max_dd
                })
            sync_summary["layers_synced"].append("L1/L2: Assets & Stats")

            # 4. Layer 4: Strategy Backtest Results
            bt_runs = client.table("backtest_runs").select("id, strategy_name, assets(symbol)").eq("batch_id", batch_id).execute().data
            for btr in bt_runs:
                strat_name = btr.get("strategy_name", "UNKNOWN")
                sym = btr.get("assets", {}).get("symbol", "ASSET") if btr.get("assets") else "ASSET"
                run_id = btr.get("id")

                # Fetch associated metrics
                metrics = client.table("backtest_metrics").select("metric_name, metric_value").eq("backtest_run_id", run_id).execute().data
                m_map = {m["metric_name"]: m["metric_value"] for m in metrics}

                tot_ret = float(m_map.get("total_return", 0.0) or 0.0)
                sh = float(m_map.get("sharpe_ratio", 0.0) or 0.0)
                dd = float(m_map.get("max_drawdown", 0.0) or 0.0)
                trades = int(m_map.get("total_trades", m_map.get("trade_count", 0)) or 0)
                win_rate = float(m_map.get("win_rate", 0.0) or 0.0)

                session.run("""
                    MATCH (b:AnalysisBatch {batch_id: $batch_id})
                    MATCH (l4:PipelineLayer {layer_number: 4})
                    MATCH (a:Asset {symbol: $symbol})
                    MERGE (s:Strategy {name: $strat_name})
                    MERGE (btr:BacktestRun {run_id: $run_id})
                    SET btr.total_return = $tot_ret,
                        btr.sharpe_ratio = $sh,
                        btr.max_drawdown = $dd,
                        btr.trade_count = $trades,
                        btr.win_rate = $win_rate,
                        btr.batch_id = $batch_id,
                        btr.asset = $symbol
                    MERGE (b)-[:PRODUCED_BACKTEST]->(btr)
                    MERGE (btr)-[:EXECUTES_STRATEGY]->(s)
                    MERGE (btr)-[:EVALUATES_ASSET]->(a)
                    MERGE (l4)-[:GENERATED_RUN]->(btr)
                """, {
                    "batch_id": batch_id,
                    "run_id": run_id,
                    "strat_name": strat_name,
                    "symbol": sym,
                    "tot_ret": tot_ret,
                    "sh": sh,
                    "dd": dd,
                    "trades": trades,
                    "win_rate": win_rate
                })
            sync_summary["layers_synced"].append("L4: Backtest Runs")

            # 5. Layer 5: Market Regimes Breakdown
            regimes_data = client.table("market_regimes").select("regime").eq("batch_id", batch_id).execute().data
            regime_counts = {}
            for r in regimes_data:
                lbl = r.get("regime", "UNKNOWN")
                regime_counts[lbl] = regime_counts.get(lbl, 0) + 1

            for r_name, count in regime_counts.items():
                session.run("""
                    MATCH (b:AnalysisBatch {batch_id: $batch_id})
                    MATCH (l5:PipelineLayer {layer_number: 5})
                    MERGE (reg:MarketRegime {name: $reg_name})
                    MERGE (b)-[d:DETECTED_REGIME {batch_id: $batch_id}]->(reg)
                    SET d.days_count = $count,
                        d.percentage = $pct
                    MERGE (l5)-[:CLASSIFIED_REGIME]->(reg)
                """, {
                    "batch_id": batch_id,
                    "reg_name": r_name,
                    "count": count,
                    "pct": (count / len(regimes_data) * 100) if regimes_data else 0.0
                })
            sync_summary["layers_synced"].append("L5: Market Regimes")

            # 6. Layer 6: Portfolio Optimization
            opt_runs = client.table("portfolio_optimization_runs").select("id, objective, status").eq("batch_id", batch_id).execute().data
            for r in opt_runs:
                allocs = client.table("portfolio_allocations").select("asset_symbol, continuous_weight, discrete_weight, expected_return, expected_volatility").eq("run_id", r["id"]).execute().data
                alloc_map = {a["asset_symbol"]: {"continuous": a["continuous_weight"], "discrete": a["discrete_weight"]} for a in allocs}

                session.run("""
                    MATCH (b:AnalysisBatch {batch_id: $batch_id})
                    MATCH (l6:PipelineLayer {layer_number: 6})
                    MERGE (opt:PortfolioOptimization {run_id: $run_id})
                    SET opt.objective = $objective,
                        opt.batch_id = $batch_id,
                        opt.allocations = $allocations
                    MERGE (b)-[:PRODUCED_OPTIMIZATION]->(opt)
                    MERGE (l6)-[:COMPUTED_OPTIMIZATION]->(opt)
                """, {
                    "batch_id": batch_id,
                    "run_id": r["id"],
                    "objective": r.get("objective"),
                    "allocations": str(alloc_map)
                })
            sync_summary["layers_synced"].append("L6: Portfolio Optimization")

            # 7. Layer 7: QUBO Results
            qubo_runs = client.table("qubo_runs").select("id, risk_weight, return_weight, num_binary_variables").eq("batch_id", batch_id).execute().data
            for qr in qubo_runs:
                q_res = client.table("qubo_results").select("solver_name, qubo_objective, btc_weight, gold_weight, nvda_weight, expected_return, volatility, sharpe_ratio").eq("qubo_run_id", qr["id"]).execute().data
                for sol in q_res:
                    session.run("""
                        MATCH (b:AnalysisBatch {batch_id: $batch_id})
                        MATCH (l7:PipelineLayer {layer_number: 7})
                        MERGE (solver:QUBOSolver {name: $solver_name})
                        MERGE (qr:QUBOResult {run_id: $run_id, solver: $solver_name})
                        SET qr.qubo_objective = $obj,
                            qr.btc_weight = $btc_w,
                            qr.gold_weight = $gold_w,
                            qr.nvda_weight = $nvda_w,
                            qr.expected_return = $exp_ret,
                            qr.volatility = $vol,
                            qr.sharpe_ratio = $sharpe,
                            qr.batch_id = $batch_id
                        MERGE (b)-[:PRODUCED_QUBO_RESULT]->(qr)
                        MERGE (qr)-[:SOLVED_BY]->(solver)
                        MERGE (l7)-[:EXECUTED_QUBO]->(qr)
                    """, {
                        "batch_id": batch_id,
                        "run_id": qr["id"],
                        "solver_name": sol.get("solver_name"),
                        "obj": sol.get("qubo_objective"),
                        "btc_w": sol.get("btc_weight"),
                        "gold_w": sol.get("gold_weight"),
                        "nvda_w": sol.get("nvda_weight"),
                        "exp_ret": sol.get("expected_return"),
                        "vol": sol.get("volatility"),
                        "sharpe": sol.get("sharpe_ratio")
                    })
            sync_summary["layers_synced"].append("L7: QUBO Quantum-Inspired Results")

        print("  Knowledge Graph synchronization completed successfully!")
        print(f"  Layers Synced: {', '.join(sync_summary['layers_synced'])}")
        return sync_summary

    except Exception as exc:
        print(f"  [ERROR] Knowledge graph sync error: {exc}")
        sync_summary["error"] = str(exc)
        return sync_summary
    finally:
        driver.close()


if __name__ == "__main__":
    _b = sys.argv[1] if len(sys.argv) > 1 else "TEST_BATCH_01"
    res = sync_batch_to_neo4j(_b)
    print(res)
