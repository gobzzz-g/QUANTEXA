<div align="center">
  
# QuantExa 📈
**Premium Quantitative Market Intelligence Terminal**

A comprehensive, institutional-grade platform for financial research, quantitative backtesting, market regime analysis, and financial knowledge graph exploration.

</div>

---

## 🌟 Overview

QuantExa is a modern financial intelligence application designed to collect historical market data, compute complex risk metrics, perform cross-asset correlation analysis, backtest trading strategies, and visualize complex financial relationships.

The platform provides a premium terminal-style UI with dynamic Light and Dark modes, leveraging powerful charting and force-directed graph layouts for unparalleled data exploration.

## 🚀 Key Features

*   **Terminal Dashboard:** Institutional-grade overview displaying real-time metrics, CAGRs, Sharpe ratios, drawdowns, and volatility across major assets.
*   **Strategy Lab & Backtesting:** Build, simulate, and analyze trading strategies. Evaluates strategies with realistic execution (next-day open), transaction costs (commissions & slippage), and sizing against Buy-and-Hold benchmarks.
*   **Financial Knowledge Graph:** A high-density, force-directed canvas that maps real financial entities (nodes) and their relationships (edges). Features include `Sequential`, `Radial`, and `Force Graph` algorithms, cluster bounding, and dynamic zoom capabilities.
*   **Correlation & Risk Engine:** Heatmaps and scatter plots comparing asset behavior.
*   **Market Regimes:** Machine-learning-style classification of market trends and volatility regimes using expanding window metrics.
*   **Global Theme System:** A sophisticated token-based Light/Dark theme system seamlessly transitioning across the UI, Plotly charts, and D3 knowledge graphs.

## 🛠️ Technology Stack

**Frontend:**
- React (Vite) & TypeScript
- Tailwind CSS (v4) with custom semantic tokens
- Plotly.js (Dynamic thematic charting)
- React-Force-Graph-2D (Canvas-based D3 visualizations)
- Lucide React (Icons)

**Backend:**
- Python & FastAPI
- Supabase (PostgreSQL)
- yfinance (Market Data integration)
- Pandas & NumPy (Quantitative Analysis)

## 📦 Setup & Installation

### 1. Prerequisites
Ensure you have `Node.js` and `Python 3.10+` installed on your machine.

### 2. Clone the Repository
```bash
git clone https://github.com/your-org/quantexa.git
cd quantexa
```

### 3. Backend Setup
Set up your Python virtual environment and install dependencies:
```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r backend/requirements.txt
```

Start the FastAPI server:
```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend Setup
Open a new terminal window, navigate to the frontend, and install dependencies:
```bash
cd frontend
npm install
```

Start the Vite development server:
```bash
npm run dev
```

The application will be available at `http://localhost:3001`.

## 🧪 Quantitative Assumptions & Bias Controls

*   **No Look-Ahead Bias:** Position targets are generated at the close of day *t* and executed at the open of day *t+1*.
*   **Realistic Execution:** Transaction costs (slippage + commission) are strictly applied to every executed trade.
*   **Regime Calculation:** Evaluated using expanding historical windows to prevent data leakage from the future sample.

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
