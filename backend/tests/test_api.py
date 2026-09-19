import pytest
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200

def test_assets():
    response = client.get("/api/assets")
    assert response.status_code == 200
    assert "BTC-USD" in response.json()

def test_provenance_metadata(mock_data_dir, sample_ohlcv):
    import os
    sample_ohlcv.to_csv(os.path.join(mock_data_dir["seed_dir"], "BTC-USD.csv"))
    
    response = client.get("/api/prices?asset=BTC-USD")
    assert response.status_code == 200
    data = response.json()
    assert "provenance" in data
    prov = data["provenance"]
    assert prov["ticker"] == "BTC-USD"
    assert "data_source" in prov
    assert "fetched_at" in prov
    assert "first_bar" in prov
    assert "last_bar" in prov
    assert prov["data_source"] == "seed"

def test_comparison_output(mock_data_dir, sample_ohlcv):
    import os
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "Open": range(100, 200),
        "High": range(105, 205),
        "Low": range(95, 195),
        "Close": range(102, 202),
        "Volume": [1000]*100
    }, index=dates)
    df.to_csv(os.path.join(mock_data_dir["seed_dir"], "BTC-USD.csv"))
    
    payload = {
        "asset": "BTC-USD",
        "strategy": "sma_crossover",
        "params": {"fast": 2, "slow": 5},
        "initial_capital": 10000.0,
        "commission_pct": 0.0,
        "slippage_bps": 0.0,
        "position_sizing": 1.0,
        "risk_free_rate": 0.0
    }
    response = client.post("/api/backtest", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    assert "verdict" in data
    verdict = data["verdict"]
    assert "The strategy returned" in verdict
    
    assert "provenance" in data
    assert "strategy" in data
    assert "benchmark" in data

def test_overview_metrics_returns_real_data(mock_data_dir, sample_ohlcv):
    import os
    sample_ohlcv.to_csv(os.path.join(mock_data_dir["seed_dir"], "BTC-USD.csv"))
    
    response = client.get("/api/metrics?asset=BTC-USD")
    assert response.status_code == 200
    data = response.json()
    assert "provenance" in data
    assert "cagr" in data
    assert "annualized_volatility" in data
    assert "sharpe" in data
    assert "max_drawdown" in data
    assert "current_price" in data

def test_overview_handles_api_failure():
    response = client.get("/api/metrics?asset=INVALID-ASSET")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Asset not found"

def test_overview_handles_empty_data(mock_data_dir):
    import os
    # Create an empty CSV with just headers
    pd.DataFrame(columns=["Date","Open","High","Low","Close","Volume"]).set_index("Date").to_csv(os.path.join(mock_data_dir["seed_dir"], "BTC-USD.csv"))
    
    response = client.get("/api/metrics?asset=BTC-USD")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Empty data for asset"

def test_correlation_returns_data(mock_data_dir, sample_ohlcv):
    import os
    sample_ohlcv.to_csv(os.path.join(mock_data_dir["seed_dir"], "BTC-USD.csv"))
    sample_ohlcv.to_csv(os.path.join(mock_data_dir["seed_dir"], "NVDA.csv"))
    
    response = client.get("/api/correlation")
    assert response.status_code == 200
    data = response.json()
    assert "assets" in data
    assert "matrix" in data
    assert len(data["assets"]) > 0
