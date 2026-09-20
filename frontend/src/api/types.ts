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

export interface AssetExplorerResponse {
  batch_id: string;
  symbol: string;
  name: string;
  asset_class: string;
  profile: {
    name: string;
    symbol: string;
    asset_class: string;
    data_source: string;
    last_updated: string;
    total_observations: number;
    annualized_return: number;
    annualized_volatility: number;
    sharpe_ratio: number;
    max_drawdown: number;
  };
  price_volume: {
    dates: string[];
    open: number[];
    high: number[];
    low: number[];
    close: number[];
    volume: number[];
  };
  rolling_returns: {
    window_days: number;
    label: string;
    dates: string[];
    returns: number[];
  };
  drawdown: {
    dates: string[];
    drawdown: number[];
  };
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

// ── Layer 4 (Supabase pre-computed results) types ─────────────────────────

export interface Layer4Run {
  run_id: string;
  strategy: string;
  symbol: string;
  name: string;
  asset_type: string;
  parameters: Record<string, number>;
  initial_capital: number;
  transaction_cost_rate: number;
  slippage_rate: number;
  start_date: string;
  end_date: string;
  status: string;
  metrics: Record<string, number>;
  // convenience top-level fields
  total_return: number;
  annualized_return: number;
  annualized_volatility: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  n_trades: number;
  total_transaction_costs: number;
  final_portfolio_value: number;
}

export interface Layer4BatchRunsResponse {
  batch_id: string;
  runs: Layer4Run[];
}

export interface Layer4EquityPoint {
  date: string;
  portfolio_value: number;
  daily_return: number;
  daily_pnl: number;
  position: number;
  close_price: number;
}

export interface Layer4EquityResponse {
  run_id: string;
  batch_id: string;
  strategy: string;
  symbol: string;
  equity: Layer4EquityPoint[];
}

export interface Layer4Trade {
  signal_date: string;
  entry_date: string;
  entry_price: number;
  exit_date: string | null;
  exit_price: number | null;
  units: number;
  entry_value: number;
  exit_value: number | null;
  entry_transaction_cost: number;
  exit_transaction_cost: number;
  gross_pnl: number | null;
  net_pnl: number | null;
  return_pct: number | null;
  holding_period_days: number | null;
  status: string;
}

export interface Layer4TradesResponse {
  run_id: string;
  batch_id: string;
  strategy: string;
  symbol: string;
  trades: Layer4Trade[];
}

export interface RollingSeriesItem {
  pair: string;
  asset_1: string;
  asset_2: string;
  window_days: number;
  dates: string[];
  correlations: number[];
  latest_correlation: number | null;
}

export interface RiskInputItem {
  symbol: string;
  name: string;
  asset_type: string;
  annualized_volatility: number;
  sharpe_ratio: number;
  max_drawdown: number;
  annualized_return: number;
}

export interface CorrelationResponse {
  batch_id?: string;
  batch_name?: string;
  data_through?: string | null;
  assets: string[];
  matrix: number[][];
  window?: string;
  windows_available?: string[];
  rolling_series?: RollingSeriesItem[];
  risk_inputs?: RiskInputItem[];
  covariance_matrix?: number[][];
  error?: string;
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
  markdown_report?: string;
}

export interface MarketAnalysisResponse {
  batch_id?: string;
  chart_data: Record<string, { dates: string[]; rebased: number[]; name?: string }>;
  breadth: {
    advancing: number;
    declining: number;
    unchanged: number;
    total: number;
    ad_ratio?: string;
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
  sector_performance?: Record<string, number>;
  kpis: {
    tracked_assets: number;
    advancing?: number;
    declining?: number;
    unchanged?: number;
    avg_period_return?: number;
    avg_return?: number;
    highest_performer?: string;
    highest_period_return?: number;
    lowest_performer?: string;
    lowest_period_return?: number;
    best_performer?: string;
    worst_performer?: string;
    data_through: string;
    lookback?: string;
  };
}
