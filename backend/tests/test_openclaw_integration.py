"""End-to-End Integration Test for OpenClaw AI Research Agent in QuantExa."""

import sys
import json
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openclaw.tools.quantexa_tools import quantexa_tools
from openclaw.agent.orchestrator import run_openclaw_research


def test_quantexa_tools_direct():
    print("\n--- 1. Testing QuantExa Tools Adapter ---")
    assets = quantexa_tools.get_available_assets()
    print(f"Available assets retrieved: {list(assets.keys())}")
    assert "BTC-USD" in assets
    assert "NVDA" in assets

    # Metrics
    btc_metrics = quantexa_tools.calculate_risk_metrics("BTC-USD")
    print(f"BTC-USD metrics: CAGR={btc_metrics.get('cagr'):.4f}, Sharpe={btc_metrics.get('sharpe'):.4f}, Vol={btc_metrics.get('annualized_volatility'):.4f}")
    assert "cagr" in btc_metrics
    assert "sharpe" in btc_metrics

    # Correlation
    corr = quantexa_tools.calculate_correlation()
    print(f"Correlation assets: {corr.get('assets')}")
    assert len(corr.get("matrix", [])) > 0

    # Knowledge Graph
    graph = quantexa_tools.query_financial_knowledge_graph()
    print(f"Knowledge Graph: {len(graph.get('nodes', []))} nodes, {len(graph.get('links', []))} links")
    print("✓ All QuantExa tools connected successfully.")


def test_single_asset_research():
    print("\n--- 2. Testing Single-Asset Research Query ---")
    query = "Analyze BTC from 2022 to 2026."
    res = run_openclaw_research(query)
    print("Orchestration steps:")
    for s in res["orchestration_steps"]:
        print(f"  [{s['status']}] {s['step']}: {s['detail']}")

    print("\nFindings:")
    for f in res["findings"]:
        print(f"  [{f['category']}]: {f['content']}")

    print(f"\nAI Conclusion: {res['conclusion']}")

    assert "BTC-USD" in res["assets_analyzed"]
    assert len(res["orchestration_steps"]) >= 3
    assert len(res["findings"]) >= 2
    assert len(res["conclusion"]) > 10
    print("✓ Single-asset research test passed.")


def test_multi_asset_comparison():
    print("\n--- 3. Testing Multi-Asset Comparison Research Query ---")
    query = "Compare BTC and NVIDIA from 2022 to 2026 using returns, volatility, Sharpe ratio and maximum drawdown."
    res = run_openclaw_research(query)
    print("Orchestration steps:")
    for s in res["orchestration_steps"]:
        print(f"  [{s['status']}] {s['step']}: {s['detail']}")

    print("\nFindings:")
    for f in res["findings"]:
        print(f"  [{f['category']}]: {f['content']}")

    print(f"\nAI Conclusion: {res['conclusion']}")

    assert "BTC-USD" in res["assets_analyzed"]
    assert "NVDA" in res["assets_analyzed"]
    assert any(f["category"] == "Performance" for f in res["findings"])
    assert any(f["category"] == "Risk" for f in res["findings"])
    assert any(f["category"] == "Correlation" for f in res["findings"])
    assert any(f["category"] == "Context" for f in res["findings"])
    print("✓ Multi-asset comparison research test passed.")


if __name__ == "__main__":
    test_quantexa_tools_direct()
    test_single_asset_research()
    test_multi_asset_comparison()
    print("\n==========================================")
    print("ALL OPENCLAW INTEGRATION TESTS PASSED!")
    print("==========================================")
