export interface DataProvenance {
  ticker: string;
  instrument_name: string;
  data_source: string;
  first_bar: string;
  last_bar: string;
  fetched_at: string;
}

export interface AssetConfig {
  ticker: string;
  name: string;
  calendar_days: number;
  asset_class?: string;
}

export interface AssetsResponse {
  [ticker: string]: AssetConfig;
}

export interface PricesResponse {
  provenance: DataProvenance;
  dates: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  volume: number[];
  rebased: number[];
}

export interface MetricsResponse {
  provenance: DataProvenance;
  cagr: number;
  annualized_volatility: number;
  sharpe: number;
  max_drawdown: number;
  current_price: number;
}

export interface BacktestMetrics {
  return: number;
  cagr: number;
  sharpe: number;
  sortino: number;
  volatility: number;
  max_drawdown: number;
  calmar: number;
  win_rate: number;
  profit_factor: number;
  trade_count: number;
  exposure: number;
  total_fees: number;
}

export interface Trade {
  entry_date: string;
  entry_price: number;
  exit_date?: string;
  exit_price?: number;
  units: number;
  fees: number;
  pnl?: number;
}

export interface BacktestResponse {
  strategy: BacktestMetrics;
  benchmark: BacktestMetrics;
  trades: Trade[];
  equity_curve: Record<string, number>;
  benchmark_curve: Record<string, number>;
  verdict: string;
  provenance: DataProvenance;
}

export interface StrategyParams {
  fast?: number;
  slow?: number;
  lookback?: number;
  threshold?: number;
  z_enter?: number;
  z_exit?: number;
}

export interface BacktestRequest {
  asset: string;
  strategy: string;
  params: StrategyParams;
  initial_capital: number;
  position_sizing: number;
  commission_pct: number;
  slippage_bps: number;
  risk_free_rate: number;
}

export interface CorrelationResponse {
  assets: string[];
  matrix: number[][];
}

export interface RegimesResponse {
  provenance: DataProvenance;
  dates: string[];
  bull_bear: number[];
  volatility: number[];
}

export interface RobustnessResponse {
  provenance: DataProvenance;
  results: Array<{
    [key: string]: any;
    cagr: number;
    sharpe: number;
    max_drawdown: number;
  }>;
}

export interface PortfolioOptimizationResult {
  method: string;
  weights: Record<string, number>;
  expected_return: number;
  volatility: number;
  sharpe_ratio: number;
  qubo_cost?: number; // Only for quantum baseline
}

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  description?: string;
  metrics?: Record<string, string>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  links: GraphEdge[];
}

export interface GraphContextResponse {
  entity: GraphNode;
  relationships: GraphEdge[];
  related_entities: GraphNode[];
}

export interface PortfolioResponse {
  assets: string[];
  optimization: PortfolioOptimizationResult;
  cov_matrix: number[][];
  expected_returns: Record<string, number>;
}

export interface ResearchResponse {
  query: string;
  assets_analyzed: string[];
  orchestration_steps: Array<{
    step: string;
    status: string;
    detail: string;
  }>;
  findings: Array<{
    category: string;
    content: string;
  }>;
  conclusion: string;
}

export interface MarketAnalysisResponse {
  chart_data: Record<string, { dates: string[], rebased: number[] }>;
  breadth: {
    advancing: number;
    declining: number;
    unchanged: number;
    total: number;
  };
  monitor: Array<{
    symbol: string;
    name: string;
    asset_class: string;
    current_price: number;
    daily_return: number;
    period_return: number;
    volatility: number;
  }>;
  sector_performance: Record<string, number>;
  kpis: {
    tracked_assets: number;
    avg_return: number;
    avg_volatility: number;
    best_performer: string;
    worst_performer: string;
    data_through: string;
  };
}
