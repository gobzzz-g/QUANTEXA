# Requirements Map

## [REQ] Feature Traceability
| Requirement | Component | File | Test File |
|-------------|-----------|------|-----------|
| **Data Provenance**: Every response contains ticker, source, as_of | Data Layer, API | `backend/app/data/loader.py`, `backend/app/api/endpoints.py` | `backend/tests/test_api.py::test_provenance_metadata` |
| **Data Cleansing**: ffill max 3 days, drop > 3 days, >0 prices | Data Layer | `backend/app/data/cleaning.py` | `backend/tests/test_data.py::test_data_cleaning_rules` |
| **No Lookahead Execution**: Signal on day t executes on day t+1 Open | Backtest Engine | `backend/app/backtest/engine.py` | `backend/tests/test_backtest.py::test_execution_rules` |
| **Benchmark**: Buy & Hold entering open of first bar | Backtest Engine | `backend/app/backtest/engine.py` | `backend/tests/test_backtest.py::test_benchmark` |
| **Fees & Slippage**: Deducted correctly | Backtest Engine | `backend/app/backtest/engine.py` | `backend/tests/test_backtest.py::test_higher_fees_lower_equity` |
| **Risk Metrics**: Sharpe, Sortino, Calmar, Max DD | Indicators | `backend/app/indicators/metrics.py` | `backend/tests/test_indicators.py` |
| **Regimes**: Expanding window Bull/Bear & Volatility | Regimes | `backend/app/regimes/analysis.py` | - |
| **Robustness**: Parameter grid evaluation | Robustness | `backend/app/robustness/sensitivity.py` | - |
| **Frontend UI**: Shows persistent provenance banner | Frontend | `frontend/src/components/ProvenanceBanner.tsx` | - |
| **Verdict**: Compare Strategy to Benchmark with neutral tone | API / Engine | `backend/app/backtest/engine.py` | `backend/tests/test_api.py::test_comparison_output` |

## [ENH] Engineering Additions
- **Seed Data Fallback**: When yfinance fails, it correctly defaults to the seed data with `data_source="seed"`.
- **Synthetic Test Fixtures**: Isolated network dependencies using pytest `monkeypatch` and generated synthetic sine waves to rigorously test indicator correctness without relying on API up-time.
- **Glassmorphism Aesthetic**: Added premium UI CSS with vibrant gradients and lucide-react icons.
