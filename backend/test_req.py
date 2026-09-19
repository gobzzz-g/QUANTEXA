from fastapi.testclient import TestClient
from app.main import app
import traceback

client = TestClient(app)
payload = {
    "asset": "BTC-USD",
    "strategy": "sma_crossover",
    "params": {"fast": 20, "slow": 50},
    "initial_capital": 10000.0,
    "commission_pct": 0.001,
    "slippage_bps": 5.0,
    "position_sizing": 1.0,
    "risk_free_rate": 0.02
}

try:
    response = client.post("/api/backtest", json=payload)
    print("Status:", response.status_code)
    if response.status_code != 200:
        print(response.json())
except Exception as e:
    traceback.print_exc()
