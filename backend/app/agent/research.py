"""QuantExa AI Research Integration Hook with OpenClaw.

Delegates incoming natural language research queries to OpenClaw AI Research Agent,
which plans tasks across skills, invokes deterministic QuantExa calculation tools,
and returns structured research insights.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("quantexa.agent.research")

# Ensure workspace root is on Python path for openclaw package imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from openclaw.agent.orchestrator import run_openclaw_research
    OPENCLAW_AVAILABLE = True
except Exception as e:
    logger.warning(f"Could not import OpenClaw orchestrator directly: {e}")
    OPENCLAW_AVAILABLE = False


def run_research_query(query: str, asset_context: Optional[List[str]] = None, batch_id: Optional[str] = None) -> Dict[str, Any]:
    """Execute AI Research query via OpenClaw Research Agent."""
    if OPENCLAW_AVAILABLE:
        try:
            import importlib
            import openclaw.agent.orchestrator as orchestrator_mod
            importlib.reload(orchestrator_mod)
            return orchestrator_mod.run_openclaw_research(query, asset_context, batch_id=batch_id)
        except Exception as err:
            logger.error(f"OpenClaw execution error: {err}", exc_info=True)
            # Return structured error response preserving UI contract
            return {
                "query": query,
                "assets_analyzed": asset_context or ["BTC-USD", "NVDA"],
                "orchestration_steps": [
                    {"step": "OpenClaw Research Agent", "status": "failed", "detail": f"Error during orchestration: {str(err)}"}
                ],
                "findings": [
                    {"category": "Error", "content": f"Failed to complete research execution: {str(err)}"}
                ],
                "conclusion": "Unable to formulate a research conclusion due to an upstream tool/API error."
            }

    # Fallback if OpenClaw module cannot be loaded
    return {
        "query": query,
        "assets_analyzed": asset_context or ["BTC-USD", "NVDA"],
        "orchestration_steps": [
            {"step": "OpenClaw Agent Discovery", "status": "failed", "detail": "OpenClaw package not initialized"}
        ],
        "findings": [
            {"category": "System", "content": "OpenClaw AI Research Agent is not configured in the active environment."}
        ],
        "conclusion": "Please ensure OpenClaw environment is properly configured."
    }
