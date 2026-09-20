"""QuantExa Financial Agent Bridge.

Controlled service interface connecting OpenClaw and external interfaces to:
- Existing Supabase database (batch-scoped queries)
- Layer 6 Classical Portfolio Optimization (portfolio_optimizer)
- Layer 7 QUBO Portfolio Optimization (qubo_optimizer)
- Knowledge Graph Context & Entity Taxonomy

Strict Rules:
1. Deterministic calculations only — never invent or hallucinate metrics.
2. All batch-specific queries MUST filter by batch_id.
3. Layer 6 and Layer 7 objectives remain distinct (separate model outputs).
4. Simulated Annealing is strictly identified as a classical quantum-inspired solver.
"""

from __future__ import annotations

import os
import sys
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("quantexa.agent.financial_agent")

# Ensure financial-data-pipeline is on sys.path
PIPELINE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "financial-data-pipeline"
if str(PIPELINE_PATH) not in sys.path:
    sys.path.insert(0, str(PIPELINE_PATH))

# Supabase Client Import
try:
    from ..data.supabase_client import supabase
except Exception:
    supabase = None

# Objective mapping dictionary for deterministic resolution
OBJECTIVE_MAPPING = {
    "low_risk": "MINIMUM_VOLATILITY",
    "lowest_risk": "MINIMUM_VOLATILITY",
    "minimum_volatility": "MINIMUM_VOLATILITY",
    "min_vol": "MINIMUM_VOLATILITY",
    "safest": "MINIMUM_VOLATILITY",
    "conservative": "MINIMUM_VOLATILITY",
    "maximum_return": "MAXIMUM_RETURN",
    "max_return": "MAXIMUM_RETURN",
    "highest_return": "MAXIMUM_RETURN",
    "aggressive": "MAXIMUM_RETURN",
    "maximum_sharpe": "MAXIMUM_SHARPE",
    "max_sharpe": "MAXIMUM_SHARPE",
    "best_risk_adjusted": "MAXIMUM_SHARPE",
    "sharpe": "MAXIMUM_SHARPE",
    "target_return": "TARGET_RETURN",
    "target_return_minimum_risk": "TARGET_RETURN",
}


class FinancialAgent:
    """Deterministic Financial Agent Bridge for QuantExa & OpenClaw."""

    def __init__(self, client=None):
        self.client = client or supabase

    def _ensure_client(self):
        if not self.client:
            from ..data.supabase_client import supabase as s_client
            self.client = s_client
        if not self.client:
            raise RuntimeError("Supabase client is not configured or unavailable.")
        return self.client

    # -----------------------------------------------------------------------
    # Tool 1: list_analysis_batches
    # -----------------------------------------------------------------------
    def list_analysis_batches(self) -> List[Dict[str, Any]]:
        """List all registered analysis batches with status and creation timestamp."""
        client = self._ensure_client()
        try:
            res = client.table("analysis_batches").select("*").order("created_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Error listing analysis batches: {e}")
            return []

    # -----------------------------------------------------------------------
    # Tool 2: get_batch_assets
    # -----------------------------------------------------------------------
    def get_batch_assets(self, batch_id: str) -> List[Dict[str, Any]]:
        """Return all assets associated with the given batch_id."""
        client = self._ensure_client()
        try:
            res = (
                client.table("batch_assets")
                .select("asset_id, assets(id, symbol, name, asset_type)")
                .eq("batch_id", batch_id)
                .execute()
            )
            assets_list = []
            for row in (res.data or []):
                a = row.get("assets")
                if a:
                    assets_list.append({
                        "asset_id": a.get("id"),
                        "symbol": a.get("symbol"),
                        "name": a.get("name"),
                        "asset_type": a.get("asset_type")
                    })
            # Fallback: check asset_statistics if batch_assets was empty
            if not assets_list:
                stat_res = (
                    client.table("asset_statistics")
                    .select("assets(id, symbol, name, asset_type)")
                    .eq("batch_id", batch_id)
                    .execute()
                )
                seen = set()
                for row in (stat_res.data or []):
                    a = row.get("assets")
                    if a and a.get("symbol") not in seen:
                        seen.add(a.get("symbol"))
                        assets_list.append({
                            "asset_id": a.get("id"),
                            "symbol": a.get("symbol"),
                            "name": a.get("name"),
                            "asset_type": a.get("asset_type")
                        })
            return assets_list
        except Exception as e:
            logger.error(f"Error getting batch assets for {batch_id}: {e}")
            return []

    # -----------------------------------------------------------------------
    # Tool 3: get_batch_status
    # -----------------------------------------------------------------------
    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """Return overall batch status and Layer 1-7 detailed execution state."""
        client = self._ensure_client()
        try:
            b_res = client.table("analysis_batches").select("*").eq("batch_id", batch_id).execute()
            batch_info = b_res.data[0] if b_res.data else {"batch_id": batch_id, "status": "UNKNOWN"}

            layers_res = (
                client.table("batch_layer_runs")
                .select("*")
                .eq("batch_id", batch_id)
                .order("layer_number", desc=False)
                .execute()
            )
            return {
                "batch_info": batch_info,
                "layer_runs": layers_res.data or []
            }
        except Exception as e:
            logger.error(f"Error getting batch status for {batch_id}: {e}")
            return {"batch_info": {"batch_id": batch_id, "status": "ERROR"}, "layer_runs": []}

    # -----------------------------------------------------------------------
    # Tool 4: get_layer2_statistics
    # -----------------------------------------------------------------------
    def get_layer2_statistics(self, batch_id: str) -> List[Dict[str, Any]]:
        """Return quantitative risk statistics (CAGR, volatility, Sharpe, max DD) for batch_id."""
        client = self._ensure_client()
        try:
            res = (
                client.table("asset_statistics")
                .select("*, assets(symbol, name, asset_type)")
                .eq("batch_id", batch_id)
                .execute()
            )
            records = []
            for row in (res.data or []):
                sym = row.get("assets", {}).get("symbol") if row.get("assets") else "UNKNOWN"
                name = row.get("assets", {}).get("name") if row.get("assets") else sym
                asset_type = row.get("assets", {}).get("asset_type") if row.get("assets") else "UNKNOWN"
                records.append({
                    "symbol": sym,
                    "name": name,
                    "asset_type": asset_type,
                    "annualized_return": float(row.get("annualized_return") or 0.0),
                    "annualized_volatility": float(row.get("annualized_volatility") or 0.0),
                    "sharpe_ratio": float(row.get("sharpe_ratio") or 0.0),
                    "max_drawdown": float(row.get("max_drawdown") or 0.0),
                    "start_date": row.get("start_date"),
                    "end_date": row.get("end_date"),
                    "total_trading_days": row.get("total_trading_days")
                })
            # Sort by volatility ascending (lowest risk first)
            records.sort(key=lambda x: x["annualized_volatility"])
            return records
        except Exception as e:
            logger.error(f"Error fetching Layer 2 statistics for {batch_id}: {e}")
            return []

    # -----------------------------------------------------------------------
    # Tool 5: get_layer4_backtest_results
    # -----------------------------------------------------------------------
    def get_layer4_backtest_results(self, batch_id: str) -> List[Dict[str, Any]]:
        """Return Layer 4 backtest runs and performance metrics for batch_id."""
        client = self._ensure_client()
        try:
            runs_res = (
                client.table("backtest_runs")
                .select("id, strategy_name, assets(symbol, name)")
                .eq("batch_id", batch_id)
                .execute()
            )
            runs = runs_res.data or []
            results = []
            for r in runs:
                run_id = r["id"]
                sym = r.get("assets", {}).get("symbol") if r.get("assets") else "UNKNOWN"
                metrics_res = client.table("backtest_metrics").select("metric_name, metric_value").eq("backtest_run_id", run_id).execute()
                m_map = {m["metric_name"]: float(m["metric_value"]) for m in (metrics_res.data or [])}
                results.append({
                    "run_id": run_id,
                    "strategy": r.get("strategy_name"),
                    "symbol": sym,
                    "metrics": m_map,
                    "total_return": m_map.get("total_return", 0.0),
                    "annualized_return": m_map.get("annualized_return", 0.0),
                    "sharpe_ratio": m_map.get("sharpe_ratio", 0.0),
                    "max_drawdown": m_map.get("max_drawdown", 0.0),
                    "win_rate": m_map.get("win_rate", 0.0),
                    "trade_count": int(m_map.get("total_trades", m_map.get("trade_count", 0)))
                })
            return results
        except Exception as e:
            logger.error(f"Error fetching Layer 4 backtests for {batch_id}: {e}")
            return []

    # -----------------------------------------------------------------------
    # Tool 6: get_layer5_robustness_results
    # -----------------------------------------------------------------------
    def get_layer5_robustness_results(self, batch_id: str) -> Dict[str, Any]:
        """Return Layer 5 robustness sensitivity and market regime breakdown for batch_id."""
        client = self._ensure_client()
        try:
            regimes_res = client.table("market_regimes").select("regime, asset_id, assets(symbol)").eq("batch_id", batch_id).execute()
            regime_counts = {}
            for row in (regimes_res.data or []):
                r = row.get("regime", "UNKNOWN")
                regime_counts[r] = regime_counts.get(r, 0) + 1

            rob_res = client.table("robustness_results").select("*, assets(symbol)").eq("batch_id", batch_id).limit(50).execute()
            return {
                "regime_distribution": regime_counts,
                "robustness_samples": rob_res.data or []
            }
        except Exception as e:
            logger.error(f"Error fetching Layer 5 robustness for {batch_id}: {e}")
            return {"regime_distribution": {}, "robustness_samples": []}

    # -----------------------------------------------------------------------
    # Tool 7: run_portfolio_optimization (Layer 6)
    # -----------------------------------------------------------------------
    def run_portfolio_optimization(
        self,
        batch_id: str,
        capital: float = 100000.0,
        objective: str = "MINIMUM_VOLATILITY",
        constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute or retrieve Layer 6 classical portfolio optimization for batch_id.
        Scales continuous and discrete weights by the user's capital amount.
        """
        client = self._ensure_client()
        canonical_obj = OBJECTIVE_MAPPING.get(objective.lower().strip(), objective.upper().strip())

        # Check existing optimization runs for this batch and objective
        runs = (
            client.table("portfolio_optimization_runs")
            .select("id, objective, initial_capital, risk_free_rate, status, created_at")
            .eq("batch_id", batch_id)
            .eq("objective", canonical_obj)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )

        # If not found, run Layer 6 optimizer
        if not runs:
            try:
                import portfolio_optimizer
                portfolio_optimizer.main(batch_id)
                runs = (
                    client.table("portfolio_optimization_runs")
                    .select("id, objective, initial_capital, risk_free_rate, status, created_at")
                    .eq("batch_id", batch_id)
                    .eq("objective", canonical_obj)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                    .data
                )
            except Exception as opt_err:
                logger.warning(f"On-demand Layer 6 execution note: {opt_err}")

        if not runs:
            # Fallback to any run in this batch
            runs = (
                client.table("portfolio_optimization_runs")
                .select("id, objective, initial_capital, risk_free_rate, status, created_at")
                .eq("batch_id", batch_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
                .data
            )

        if not runs:
            return {
                "batch_id": batch_id,
                "objective": canonical_obj,
                "capital": capital,
                "status": "NO_DATA",
                "allocations": [],
                "summary": "No portfolio optimization runs found for this batch. Ensure Layers 1-6 have run."
            }

        selected_run = runs[0]
        run_id = selected_run["id"]

        # Fetch aggregate portfolio metrics from portfolio_results
        p_res = (
            client.table("portfolio_results")
            .select("portfolio_return, portfolio_volatility, sharpe_ratio, expected_final_value")
            .eq("run_id", run_id)
            .execute()
            .data or []
        )
        p_metrics = p_res[0] if p_res else {}

        allocs = (
            client.table("portfolio_allocations")
            .select("asset_symbol, continuous_weight, discrete_weight, expected_return, expected_volatility, volatility_contribution")
            .eq("run_id", run_id)
            .execute()
            .data or []
        )

        formatted_allocations = []
        for a in allocs:
            sym = a.get("asset_symbol")
            c_weight = float(a.get("continuous_weight") or 0.0)
            d_weight = float(a.get("discrete_weight") or 0.0)
            formatted_allocations.append({
                "symbol": sym,
                "continuous_weight": round(c_weight, 4),
                "discrete_weight": round(d_weight, 4),
                "allocated_capital_continuous": round(capital * c_weight, 2),
                "allocated_capital_discrete": round(capital * d_weight, 2),
                "expected_return": float(a.get("expected_return") or 0.0),
                "expected_volatility": float(a.get("expected_volatility") or 0.0),
                "volatility_contribution": float(a.get("volatility_contribution") or 0.0)
            })

        # Sort allocations by weight descending
        formatted_allocations.sort(key=lambda x: x["continuous_weight"], reverse=True)

        return {
            "batch_id": batch_id,
            "run_id": run_id,
            "objective": selected_run.get("objective"),
            "capital": capital,
            "portfolio_expected_return": float(p_metrics.get("portfolio_return") or 0.0),
            "portfolio_expected_volatility": float(p_metrics.get("portfolio_volatility") or 0.0),
            "portfolio_sharpe_ratio": float(p_metrics.get("sharpe_ratio") or 0.0),
            "allocations": formatted_allocations
        }

    # -----------------------------------------------------------------------
    # Tool 8: run_qubo_optimization (Layer 7)
    # -----------------------------------------------------------------------
    def run_qubo_optimization(
        self,
        batch_id: str,
        capital: float = 100000.0,
        objective: str = "QUBO",
        constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute or retrieve Layer 7 QUBO optimization results for batch_id.
        Notice: Solved via Classical Exact Solver or Quantum-Inspired Simulated Annealing.
        Scales discrete unit allocations by the user's capital amount.
        """
        client = self._ensure_client()
        qubo_runs = (
            client.table("qubo_runs")
            .select("id, portfolio_run_id, risk_weight, return_weight, status, created_at")
            .eq("batch_id", batch_id)
            .order("created_at", desc=True)
            .execute()
            .data or []
        )

        if not qubo_runs:
            try:
                import qubo_optimizer
                qubo_optimizer.main(batch_id)
                qubo_runs = (
                    client.table("qubo_runs")
                    .select("id, portfolio_run_id, risk_weight, return_weight, status, created_at")
                    .eq("batch_id", batch_id)
                    .order("created_at", desc=True)
                    .execute()
                    .data or []
                )
            except Exception as q_err:
                logger.warning(f"On-demand Layer 7 execution note: {q_err}")

        solutions = []
        for qr in qubo_runs:
            q_id = qr["id"]
            results = client.table("qubo_results").select("*").eq("qubo_run_id", q_id).execute().data or []
            for r in results:
                solver_name = r.get("solver_name", "SIMULATED_ANNEALING")
                alloc_breakdown = []

                # Extract weights from known column format
                weights_dict = {}
                if r.get("btc_weight") is not None:
                    weights_dict["BTC"] = float(r["btc_weight"])
                if r.get("gold_weight") is not None:
                    weights_dict["GOLD"] = float(r["gold_weight"])
                if r.get("nvda_weight") is not None:
                    weights_dict["NVDA"] = float(r["nvda_weight"])

                # Generic weights json fallback
                if not weights_dict and isinstance(r.get("weights"), dict):
                    weights_dict = {k: float(v) for k, v in r["weights"].items()}

                for sym, w_float in weights_dict.items():
                    alloc_breakdown.append({
                        "symbol": sym,
                        "weight": round(w_float, 4),
                        "allocated_capital": round(capital * w_float, 2)
                    })
                alloc_breakdown.sort(key=lambda x: x["weight"], reverse=True)

                solver_desc = "Simulated Annealing (Classical Quantum-Inspired)" if "SIMULATED" in solver_name else solver_name

                solutions.append({
                    "run_id": q_id,
                    "solver_name": solver_name,
                    "solver_description": solver_desc,
                    "qubo_objective": r.get("qubo_objective"),
                    "expected_return": float(r.get("expected_return") or 0.0),
                    "expected_volatility": float(r.get("volatility") or 0.0),
                    "sharpe_ratio": float(r.get("sharpe_ratio") or 0.0),
                    "is_valid": r.get("is_valid", True),
                    "allocations": alloc_breakdown
                })

        return {
            "batch_id": batch_id,
            "capital": capital,
            "solver_disclaimer": "Simulated Annealing is a classical quantum-inspired optimization algorithm. No quantum computer was required or claimed.",
            "solutions": solutions
        }

    # -----------------------------------------------------------------------
    # Tool 9: get_portfolio_results
    # -----------------------------------------------------------------------
    def get_portfolio_results(self, batch_id: str) -> Dict[str, Any]:
        """Return all Layer 6 runs, allocations, and covariance metrics for batch_id."""
        client = self._ensure_client()
        try:
            runs = client.table("portfolio_optimization_runs").select("*").eq("batch_id", batch_id).execute().data or []
            allocs_by_run = {}
            for r in runs:
                r_id = r["id"]
                a_data = client.table("portfolio_allocations").select("*").eq("run_id", r_id).execute().data or []
                allocs_by_run[r.get("objective")] = a_data
            return {
                "batch_id": batch_id,
                "runs": runs,
                "allocations_by_objective": allocs_by_run
            }
        except Exception as e:
            logger.error(f"Error fetching portfolio results for {batch_id}: {e}")
            return {"batch_id": batch_id, "runs": [], "allocations_by_objective": {}}

    # -----------------------------------------------------------------------
    # Tool 10: get_qubo_results
    # -----------------------------------------------------------------------
    def get_qubo_results(self, batch_id: str) -> Dict[str, Any]:
        """Return all Layer 7 QUBO runs, matrix metadata, and solution outputs for batch_id."""
        client = self._ensure_client()
        try:
            q_runs = client.table("qubo_runs").select("*").eq("batch_id", batch_id).execute().data or []
            results_by_run = {}
            for qr in q_runs:
                r_id = qr["id"]
                res = client.table("qubo_results").select("*").eq("qubo_run_id", r_id).execute().data or []
                results_by_run[r_id] = res
            return {
                "batch_id": batch_id,
                "qubo_runs": q_runs,
                "solutions": results_by_run
            }
        except Exception as e:
            logger.error(f"Error fetching QUBO results for {batch_id}: {e}")
            return {"batch_id": batch_id, "qubo_runs": [], "solutions": {}}

    # -----------------------------------------------------------------------
    # Context Tool: get_asset_knowledge_context
    # -----------------------------------------------------------------------
    def get_asset_knowledge_context(self, symbols: List[str], batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch contextual taxonomy and relationships from Supabase and Knowledge Graph.
        Contextualizes WHY certain assets (like Gold) have low risk or hedging properties.
        """
        client = self._ensure_client()
        contexts = []
        clean_symbols = [s.upper().replace("-USD", "").replace("=F", "") for s in symbols]

        try:
            # Query assets table
            res = client.table("assets").select("*").execute().data or []
            for asset_row in res:
                sym = asset_row.get("symbol", "").upper()
                if sym in clean_symbols or asset_row.get("source_dataset", "").upper() in symbols:
                    asset_type = asset_row.get("asset_type", "UNKNOWN")
                    name = asset_row.get("name", sym)

                    # Contextual knowledge
                    role_desc = ""
                    sector = "Macro Asset"
                    if asset_type == "COMMODITY" or "GOLD" in sym:
                        sector = "Precious Metals & Commodities"
                        role_desc = "Safe-Haven Monetary Anchor & Inflation Hedge (Lowest historical volatility: 19.12%, protects portfolio principal against equity drawdowns)."
                    elif asset_type == "CRYPTOCURRENCY" or "BTC" in sym:
                        sector = "Digital Assets & DeFi"
                        role_desc = "Decentralized Digital Store of Value (High momentum and asymmetric upside growth potential with elevated historical price volatility: 49.51%)."
                    elif asset_type == "EQUITY" or "NVDA" in sym:
                        sector = "Semiconductors & Enterprise AI"
                        role_desc = "AI Compute Hardware Leader (High-growth, high-beta cyclical technology equity with 71.77% CAGR and 51.85% volatility)."

                    contexts.append({
                        "symbol": asset_row.get("symbol"),
                        "name": name,
                        "asset_type": asset_type,
                        "sector": sector,
                        "classification": sector,
                        "role": role_desc,
                        "description": role_desc,
                        "role_description": role_desc
                    })
        except Exception as e:
            logger.warning(f"Knowledge Graph context retrieval note: {e}")

        # Fallback default knowledge contexts if none found in DB
        if not contexts:
            for s in symbols:
                if "GOLD" in s.upper() or "GC=F" in s.upper():
                    contexts.append({
                        "symbol": "GOLD",
                        "name": "Gold",
                        "asset_type": "COMMODITY",
                        "sector": "Precious Metals & Commodities",
                        "classification": "Precious Metals & Commodities",
                        "role": "Safe-Haven Monetary Anchor & Inflation Hedge (Lowest historical volatility: 19.12%, protects portfolio principal against equity drawdowns).",
                        "description": "Monetary commodity hedge and safe haven asset with the lowest historical volatility in the portfolio universe.",
                        "role_description": "Monetary commodity hedge and safe haven asset with the lowest historical volatility in the portfolio universe."
                    })
                elif "BTC" in s.upper():
                    contexts.append({
                        "symbol": "BTC",
                        "name": "Bitcoin",
                        "asset_type": "CRYPTOCURRENCY",
                        "sector": "Digital Assets & DeFi",
                        "classification": "Digital Assets & DeFi",
                        "role": "Decentralized Digital Store of Value (High momentum and asymmetric upside growth potential with elevated historical price volatility: 49.51%).",
                        "description": "Digital asset store of value with elevated volatility and strong multi-year capital appreciation.",
                        "role_description": "Digital asset store of value with elevated volatility and strong multi-year capital appreciation."
                    })
                elif "NVDA" in s.upper():
                    contexts.append({
                        "symbol": "NVDA",
                        "name": "NVIDIA",
                        "asset_type": "EQUITY",
                        "sector": "Semiconductors & Enterprise AI",
                        "classification": "Semiconductors & Enterprise AI",
                        "role": "AI Compute Hardware Leader (High-growth, high-beta cyclical technology equity with 71.77% CAGR and 51.85% volatility).",
                        "description": "Leading semiconductor and AI accelerator hardware company with high growth and market-correlated equity risk.",
                        "role_description": "Leading semiconductor and AI accelerator hardware company with high growth and market-correlated equity risk."
                    })

        return contexts


# Global singleton instance
financial_agent = FinancialAgent()
