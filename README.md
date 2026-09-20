<div align="center">

# 📈 QuantExa
### **Institutional-Grade Financial Intelligence & Quantitative Analytics Terminal**

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React_18_|_Vite-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/Language-TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Language-Python_3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Tailwind CSS](https://img.shields.io/badge/Styling-Tailwind_CSS_v4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-MIT-green.style=for-the-badge)](LICENSE)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [System Architecture](#-system-architecture)
- [Key Features & Terminal Modules](#-key-features--terminal-modules)
- [Quantitative Rigor & Bias Controls](#-quantitative-rigor--bias-controls)
- [Technology Stack](#-technology-stack)
- [Getting Started](#-getting-started)
  - [Prerequisites](#1-prerequisites)
  - [Quick Start (One-Click Launcher)](#2-quick-start-one-click-launcher)
  - [Manual Setup](#3-manual-setup)
  - [Environment Variables](#4-environment-variables)
- [Data Pipeline Architecture](#-data-pipeline-architecture)
- [API Endpoints Reference](#-api-endpoints-reference)
- [License](#-license)

---

## 🌟 Overview

**QuantExa** is an institutional-grade financial research and quantitative analytics platform designed for cross-asset market intelligence, strategy backtesting, portfolio optimization, and entity graph visual analytics.

It bridges real-time market data ingestion with advanced quantitative modeling—including continuous Markowitz convex optimization, QUBO (Quadratic Unconstrained Binary Optimization) solved via simulated annealing, vectorized backtesting with zero look-ahead bias, and AI-powered natural language research tools via an OpenClaw gateway.

---

## 🏗 System Architecture

```
                               ┌───────────────────────────────────────────┐
                               │             User Interface                │
                               │  React 18 + TypeScript + Tailwind CSS v4  │
                               └─────────────────────┬─────────────────────┘
                                                     │ (REST API & WS)
                                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       QuantExa FastAPI Backend                                        │
├──────────────────────────┬─────────────────────────┬──────────────────────────┬────────────────────────┤
│     Data Engine          │    Analytics Engine     │    Backtest Engine       │   Optimization Engine  │
│  - yfinance Loader       │  - Risk & Correlation   │  - Vectorized Execution  │  - Continuous Markowitz│
│  - Data Cleaning         │  - CAGR, Sharpe, DD     │  - Zero Look-ahead       │  - QUBO Solvers        │
│  - Seed Fallback         │  - Volatility Metrics   │  - Fees & Slippage       │  - Portfolio Frontier  │
└────────────┬─────────────┴────────────┬────────────┴────────────┬─────────────┴────────────┬───────────┘
             │                          │                         │                          │
             ▼                          ▼                         ▼                          ▼
┌──────────────────────────┐ ┌────────────────────┐ ┌──────────────────────────┐ ┌──────────────────────────┐
│   PostgreSQL / Supabase  │ │ OpenClaw AI Gateway│ │ Financial Data Pipeline  │ │  Interactive Dashboards  │
│  (Historical OHLCV &     │ │  (LLM Research &   │ │   (7-Layer Automated     │ │  (Plotly.js + Canvas D3  │
│   Batch Records)         │ │   Market Agent)    │ │    Ingestion & Clean)    │ │   Knowledge Graph)       │
└──────────────────────────┘ └────────────────────┘ └──────────────────────────┘ └──────────────────────────┘
```

---

## 🚀 Key Features & Terminal Modules

QuantExa features a unified, responsive terminal interface equipped with dark/light glassmorphic UI themes:

### 1. 📊 Overview Dashboard
- Institutional executive summary featuring portfolio metrics, market performance cards, asset price tickers, CAGRs, Sharpe ratios, maximum drawdowns, and volatility metrics across major assets (Cryptocurrency, Equities, Commodities).

### 2. ⚡ Data & Pipeline Manager
- Interactive control panel for executing the **7-Layer Quantitative Data Pipeline**:
  - **Layer 1:** Ingestion, validation & price deduplication
  - **Layer 2:** Quantitative risk metrics (CAGR, Sharpe, Sortino, Max Drawdown)
  - **Layer 3:** Signal generation (SMA crossover, momentum, mean reversion)
  - **Layer 4:** Deterministic backtesting engine execution
  - **Layer 5:** Regime segmentation & parameter stress testing
  - **Layer 6:** Continuous Markowitz convex portfolio optimization
  - **Layer 7:** QUBO binary portfolio selection via simulated annealing

### 3. 📈 Market Analysis
- Interactive time-series visualizer powered by Plotly.js.
- Dual-axis candlestick charts, moving averages (SMA 20/50/200), trading volume breakdowns, and rolling volatility displays.

### 4. 🔍 Asset Explorer
- Cross-asset analytics hub providing deep-dive metrics, historical return distributions, risk profiles, asset class tags, and provenance tracking.

### 5. 🔀 Correlation & Risk Engine
- Dynamic asset correlation matrix heatmap.
- Interactive return scatter plots, rolling beta comparisons, and tail risk metrics to analyze portfolio diversification.

### 6. 🧪 Strategy Lab (Backtesting Engine)
- Vectorized, deterministic backtesting engine supporting configurable strategies:
  - **SMA Crossover** (Fast vs Slow Moving Averages)
  - **Momentum Engine** (Lookback return thresholds)
  - **Mean Reversion** (Z-Score price deviations)
- Fully customizable risk-free rate, transaction commissions, and market slippage assumptions.
- Performance verdict comparison against a passive Buy-and-Hold benchmark.

### 7. 💼 Portfolio Optimization Engine
- Continuous convex **Markowitz Mean-Variance Optimization** (Efficient Frontier, Max Sharpe, Min Volatility).
- **QUBO (Quadratic Unconstrained Binary Optimization)** solver using classical simulated annealing to solve discrete asset selection under target risk and return constraints.

### 8. 🕸 Financial Knowledge Graph
- Force-directed Canvas D3 graph mapping relationships across Financial Assets, Portfolios, Strategies, and Risk Factors.
- Supports **Force**, **Radial**, and **Sequential** graph layouts, entity filtering, node search, and interactive zooming.

### 9. 🤖 AI Research Assistant (OpenClaw Agent)
- Autonomous financial research agent integrating natural language query processing with tools for market sentiment, quantitative ratio analysis, risk diagnostics, and technical summaries.

### 10. 📄 Reports & Methodology
- Automated institutional research summary PDF report generation.
- Full mathematical transparency detailing quantitative formulas, bias controls, and indicator derivations.

---

## 🛡 Quantitative Rigor & Bias Controls

QuantExa enforces strict quantitative rules to eliminate data leakage and guarantee realistic backtest performance:

*   **Zero Look-Ahead Bias:** Signals are computed strictly using data available up to the close of day $t$. Trades execute at the **Open price of day $t+1$**.
*   **Realistic Execution Friction:** Deducts configurable commissions (e.g., 0.10%) and market slippage (e.g., 5 bps) on every rebalance trade.
*   **Multi-Calendar Alignment:** Safely handles asset calendar differences (252 equity trading days vs. 365 crypto calendar days) using strict inner joins rather than artificial forward-filling.
*   **Expanding Window Regimes:** Regimes and rolling parameters are calculated using expanding windows to avoid using future sample statistics.
*   **Data Provenance & Resilience:** Every response returns explicit data source metadata (`ticker`, `source`, `as_of`). Automated fallback to verified local seed CSV data ensures system availability even during external API downtime.

---

## 🛠 Technology Stack

### **Frontend**
- **Framework:** React 18, Vite, TypeScript
- **Styling:** Tailwind CSS v4, Custom CSS Variables, Lucide Icons
- **Charting & Visuals:** Plotly.js (`react-plotly.js`), `react-force-graph-2d` (Canvas D3)
- **State & Query Management:** `@tanstack/react-query`, Context API

### **Backend**
- **API Framework:** Python 3.10+, FastAPI, Uvicorn
- **Quantitative Engine:** NumPy, Pandas, SciPy, Scikit-learn
- **Data Integration:** yfinance API, Supabase Python Client
- **AI Agent Integration:** OpenClaw Agent Gateway (`node openclaw.mjs`), LangChain / Custom LLM tool bindings

---

## ⚙️ Getting Started

### 1. Prerequisites
- **Node.js:** v18.0.0 or higher
- **Python:** v3.10 or higher
- **Git**

### 2. Quick Start (One-Click Launcher)

On Windows, you can start all microservices (Backend, Frontend, OpenClaw Agent) simultaneously using the provided batch launcher:

```cmd
.\start_all.bat
```

This will launch:
- **FastAPI Backend:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Swagger Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **React Frontend:** [http://localhost:3000](http://localhost:3000)
- **OpenClaw Gateway:** Agent listener process

---

### 3. Manual Setup

#### Step A: Backend Setup
1. Navigate to the project root and create a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
2. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Start the FastAPI development server:
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```

#### Step B: Frontend Setup
1. Open a new terminal and navigate to the frontend folder:
   ```bash
   cd frontend
   npm install
   ```
2. Start the Vite development server:
   ```bash
   npm run dev
   ```
3. Open your browser at `http://localhost:3000`.

#### Step C: OpenClaw Agent Setup (Optional)
```bash
cd openclaw
node openclaw.mjs
```

---

### 4. Environment Variables

Create a `.env` file in the root directory if configuring cloud database or AI endpoints:

```env
SUPABASE_URL=https://your-supabase-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
OPENAI_API_KEY=your-openai-key
PORT=8000
```

---

## 🔄 Data Pipeline Architecture

The financial data pipeline can be executed manually or scheduled via the batch engine:

```bash
cd financial-data-pipeline
python run_pipeline.py BATCH_DEFAULT
```

| Layer | Module Name | Primary Responsibility |
|---|---|---|
| **L1** | Data Ingestion | OHLCV verification, missing value handling, timestamp alignment |
| **L2** | Quantitative Metrics | Rolling CAGR, Sharpe ratios, Sortino ratios, Max Drawdown calculation |
| **L3** | Signal Generation | Technical indicator signal synthesis (SMA, Momentum, Z-Score) |
| **L4** | Backtesting | Execution simulation on $t+1$ Open with commission & slippage |
| **L5** | Regimes & Sensitivity | Parameter stability grid evaluation & volatility regime mapping |
| **L6** | Continuous Convex Opt | Markowitz Mean-Variance frontier generation |
| **L7** | QUBO Solvers | Simulated annealing for combinatorial asset subset allocation |

---

## 🔌 API Endpoints Reference

### Health & System
- `GET /health` - System readiness check
- `GET /api/provenance` - Data source provenance metadata

### Market Data & Indicators
- `GET /api/assets` - List available tracked tickers
- `GET /api/data?asset={ticker}` - Retrieve historical OHLCV data
- `GET /api/overview` - Real-time metrics summary for dashboard

### Backtest Engine
- `POST /api/backtest` - Run deterministic backtesting simulation
  ```json
  {
    "asset": "BTC-USD",
    "strategy": "sma_crossover",
    "params": { "fast_period": 20, "slow_period": 50 },
    "initial_capital": 10000,
    "commission": 0.001,
    "slippage": 0.0005
  }
  ```

### Portfolio Optimization
- `POST /api/portfolio/optimize` - Continuous Markowitz optimization
- `POST /api/portfolio/qubo` - QUBO simulated annealing optimization

---

## 📄 License

This project is released under the **MIT License**. See the [LICENSE](LICENSE) file for details.
