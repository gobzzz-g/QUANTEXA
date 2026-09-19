import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { AssetsResponse, BacktestResponse, StrategyParams, Trade } from '../api/types';
import Plot from 'react-plotly.js';
import { Settings, Play, Download, AlertCircle, History, Filter } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';

const getInitialState = <T,>(key: string, defaultValue: T): T => {
  const stored = sessionStorage.getItem(key);
  if (stored) {
    try { return JSON.parse(stored); } catch { return defaultValue; }
  }
  return defaultValue;
}

export function StrategyLab() {
  const location = useLocation();
  const state = location.state as { asset?: string, strategy?: string, params?: StrategyParams } | null;

  const { data: assets } = useQuery<AssetsResponse>({
    queryKey: ['assets'],
    queryFn: async () => (await apiClient.get('/assets')).data
  });

  const [asset, setAsset] = useState<string>(() => state?.asset || getInitialState('lab_asset', 'BTC-USD'));
  const [strategy, setStrategy] = useState<string>(() => state?.strategy || getInitialState('lab_strategy', 'sma_crossover'));
  const [params, setParams] = useState<StrategyParams>(() => state?.params || getInitialState('lab_params', { fast: 20, slow: 50 }));
  const [initialCapital, setInitialCapital] = useState(() => getInitialState('lab_capital', 10000));
  const [positionSizing, setPositionSizing] = useState(() => getInitialState('lab_sizing', 1.0));
  const [commissionPct, setCommissionPct] = useState(() => getInitialState('lab_commission', 0.001));
  const [slippageBps, setSlippageBps] = useState(() => getInitialState('lab_slippage', 5.0));
  const [riskFreeRate, setRiskFreeRate] = useState(() => getInitialState('lab_rf', 0.0));
  
  const [lastRunPayload, setLastRunPayload] = useState<any>(() => getInitialState('lab_lastRun', null));

  // Auto-update if navigating from Strategy Lab
  useEffect(() => {
    if (state?.asset) setAsset(state.asset);
    if (state?.strategy) setStrategy(state.strategy);
    if (state?.params) setParams(state.params);
  }, [state]);

  // Persist form state to sessionStorage
  useEffect(() => {
    sessionStorage.setItem('lab_asset', JSON.stringify(asset));
    sessionStorage.setItem('lab_strategy', JSON.stringify(strategy));
    sessionStorage.setItem('lab_params', JSON.stringify(params));
    sessionStorage.setItem('lab_capital', JSON.stringify(initialCapital));
    sessionStorage.setItem('lab_sizing', JSON.stringify(positionSizing));
    sessionStorage.setItem('lab_commission', JSON.stringify(commissionPct));
    sessionStorage.setItem('lab_slippage', JSON.stringify(slippageBps));
    sessionStorage.setItem('lab_rf', JSON.stringify(riskFreeRate));
  }, [asset, strategy, params, initialCapital, positionSizing, commissionPct, slippageBps, riskFreeRate]);

  const { data: backtestData, isFetching: backtestLoading, error: backtestError } = useQuery<BacktestResponse, Error>({
    queryKey: ['backtest', lastRunPayload],
    queryFn: async () => {
      const res = await apiClient.post('/backtest', lastRunPayload);
      return res.data;
    },
    enabled: !!lastRunPayload,
    staleTime: Infinity, // Keep in cache indefinitely during session
  });

  const runBacktest = () => {
    const payload = {
      asset,
      strategy,
      params,
      initial_capital: initialCapital,
      position_sizing: positionSizing,
      commission_pct: commissionPct,
      slippage_bps: slippageBps,
      risk_free_rate: riskFreeRate
    };
    setLastRunPayload(payload);
    sessionStorage.setItem('lab_lastRun', JSON.stringify(payload));
  };

  const handleParamChange = (key: string, value: string) => {
    setParams({ ...params, [key]: parseFloat(value) || 0 });
  };

  const renderStrategyParams = () => {
    if (strategy === 'sma_crossover' || strategy === 'ema_trend') {
      return (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Fast Window</label>
            <input type="number" className="input-field" value={params.fast || ''} onChange={e => handleParamChange('fast', e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Slow Window</label>
            <input type="number" className="input-field" value={params.slow || ''} onChange={e => handleParamChange('slow', e.target.value)} />
          </div>
        </div>
      );
    } else if (strategy === 'momentum') {
      return (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Lookback</label>
            <input type="number" className="input-field" value={params.lookback || ''} onChange={e => handleParamChange('lookback', e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Threshold</label>
            <input type="number" step="0.01" className="input-field" value={params.threshold || ''} onChange={e => handleParamChange('threshold', e.target.value)} />
          </div>
        </div>
      );
    } else if (strategy === 'mean_reversion') {
      return (
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="block text-xs font-medium text-text-muted mb-1">Lookback</label>
            <input type="number" className="input-field" value={params.lookback || ''} onChange={e => handleParamChange('lookback', e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Entry Z-Score</label>
            <input type="number" step="0.1" className="input-field" value={params.z_enter || ''} onChange={e => handleParamChange('z_enter', e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Exit Z-Score</label>
            <input type="number" step="0.1" className="input-field" value={params.z_exit || ''} onChange={e => handleParamChange('z_exit', e.target.value)} />
          </div>
        </div>
      );
    }
  };

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Strategy Lab</h1>
        <p className="text-sm text-text-muted mt-1">Configure parameters, execute strategy simulations, and analyze performance against historical data.</p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 flex-1">
        {/* CONTROL PANEL */}
        <div className="w-full lg:w-[340px] flex-shrink-0 flex flex-col gap-6">
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="flex items-center text-sm">
                <Settings size={16} className="text-primary mr-2" /> Execution Setup
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-text-muted mb-1">Asset</label>
                  <select className="input-field py-1.5" value={asset} onChange={e => setAsset(e.target.value)}>
                    {assets && Object.entries(assets).map(([k, v]) => (
                      <option key={k} value={k}>{v.name} ({k})</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-text-muted mb-1">Strategy</label>
                  <select className="input-field py-1.5" value={strategy} onChange={e => setStrategy(e.target.value)}>
                    <option value="sma_crossover">SMA Crossover</option>
                    <option value="ema_trend">EMA Trend</option>
                    <option value="momentum">Momentum</option>
                    <option value="mean_reversion">Mean Reversion</option>
                  </select>
                </div>
              </div>

              <div className="border-t border-border pt-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-[10px] font-bold text-primary uppercase tracking-wider">Strategy Params</h3>
                  <Filter size={12} className="text-text-muted" />
                </div>
                {renderStrategyParams()}
              </div>

              <div className="border-t border-border pt-4">
                <h3 className="text-[10px] font-bold text-primary uppercase tracking-wider mb-3">Portfolio & Execution</h3>
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-text-muted mb-1">Capital ($)</label>
                      <input type="number" className="input-field" value={initialCapital} onChange={e => setInitialCapital(parseFloat(e.target.value))} />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-text-muted mb-1">Position Size</label>
                      <input type="number" step="0.1" className="input-field" value={positionSizing} onChange={e => setPositionSizing(parseFloat(e.target.value))} />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-text-muted mb-1">Commission (%)</label>
                      <input type="number" step="0.001" className="input-field" value={commissionPct} onChange={e => setCommissionPct(parseFloat(e.target.value))} />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-text-muted mb-1">Slippage (bps)</label>
                      <input type="number" step="1" className="input-field" value={slippageBps} onChange={e => setSlippageBps(parseFloat(e.target.value))} />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-text-muted mb-1">Risk-Free Rate (Annual)</label>
                    <input type="number" step="0.01" className="input-field" value={riskFreeRate} onChange={e => setRiskFreeRate(parseFloat(e.target.value))} />
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <button
                  onClick={runBacktest}
                  disabled={backtestLoading}
                  className="btn-primary w-full py-2.5 shadow-md shadow-primary/20"
                >
                  {backtestLoading ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  ) : (
                    <>
                      <Play size={16} className="mr-2" />
                      RUN BACKTEST
                    </>
                  )}
                </button>
              </div>

            </CardContent>
          </Card>
        </div>

        {/* RESULTS WORKSPACE */}
        <div className="flex-1 flex flex-col gap-6">
          {!backtestData && !backtestLoading && !backtestError && (
            <div className="flex-1 border-2 border-border border-dashed rounded-xl flex flex-col items-center justify-center text-text-muted p-12 bg-surface/30">
              <History size={48} className="mb-4 text-border" />
              <h3 className="text-lg font-medium text-text-main">Ready to Simulate</h3>
              <p className="text-sm mt-2 max-w-sm text-center">Configure execution parameters on the left and run the backtest against historical Supabase data.</p>
            </div>
          )}

          {backtestLoading && (
            <div className="flex-1 border border-border rounded-xl flex flex-col items-center justify-center p-12 bg-surface/30 animate-pulse">
              <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mb-4"></div>
              <p className="text-sm font-medium text-text-muted">Computing historical simulation...</p>
            </div>
          )}

          {backtestError && (
            <div className="flex-1 bg-negative/5 border border-negative/20 rounded-xl flex flex-col items-center justify-center p-12">
              <AlertCircle size={40} className="text-negative mb-4" />
              <h3 className="text-lg font-bold text-negative mb-2">Simulation Failed</h3>
              <p className="text-sm text-text-muted">{backtestError?.message || 'An unknown error occurred during computation.'}</p>
            </div>
          )}

          {backtestData && !backtestLoading && (
            <div className="space-y-6 animate-fade-in">
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                <ResultMetric title="Total Return" value={`${(backtestData.strategy.return * 100).toFixed(2)}%`} isNegative={backtestData.strategy.return < 0} />
                <ResultMetric title="CAGR" value={`${(backtestData.strategy.cagr * 100).toFixed(2)}%`} isNegative={backtestData.strategy.cagr < 0} />
                <ResultMetric title="Sharpe Ratio" value={backtestData.strategy.sharpe.toFixed(2)} />
                <ResultMetric title="Max Drawdown" value={`${(backtestData.strategy.max_drawdown * 100).toFixed(2)}%`} isNegative={backtestData.strategy.max_drawdown < 0} />
                <ResultMetric title="Win Rate" value={`${(backtestData.strategy.win_rate * 100).toFixed(1)}%`} />
                <ResultMetric title="Profit Factor" value={backtestData.strategy.profit_factor.toFixed(2)} />
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <Card className="xl:col-span-2 flex flex-col min-h-[450px]">
                  <CardHeader className="py-3">
                    <CardTitle className="text-sm">Equity Curve (Rebased)</CardTitle>
                  </CardHeader>
                  <div className="flex-1 w-full p-2">
                    <Plot
                      data={[
                        {
                          x: Object.keys(backtestData.equity_curve),
                          y: Object.values(backtestData.equity_curve),
                          type: 'scatter',
                          mode: 'lines',
                          name: 'Strategy',
                          line: { color: '#10B981', width: 2 }
                        },
                        {
                          x: Object.keys(backtestData.benchmark_curve),
                          y: Object.values(backtestData.benchmark_curve),
                          type: 'scatter',
                          mode: 'lines',
                          name: 'Buy & Hold',
                          line: { color: 'var(--text-muted)', width: 1.5, dash: 'dot' }
                        }
                      ]}
                      layout={{
                        autosize: true,
                        paper_bgcolor: 'transparent',
                        plot_bgcolor: 'transparent',
                        margin: { t: 20, r: 20, l: 40, b: 30 },
                        xaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true },
                        yaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true },
                        font: { color: 'var(--text-main)', family: 'Inter' },
                        legend: { orientation: 'h', y: 1.05, x: 0 },
                        hovermode: 'x unified'
                      }}
                      useResizeHandler={true}
                      style={{ width: '100%', height: '100%' }}
                      config={{ displayModeBar: false, responsive: true }}
                    />
                  </div>
                </Card>

                <Card>
                  <CardHeader className="py-3">
                    <CardTitle className="text-sm">Performance Profile</CardTitle>
                  </CardHeader>
                  <div className="p-0 overflow-hidden">
                    <table className="w-full text-sm text-left">
                      <thead className="text-[10px] uppercase text-text-muted bg-surface-hover/50 border-b border-border">
                        <tr>
                          <th className="py-2 px-4 font-medium">Metric</th>
                          <th className="py-2 px-4 font-medium text-right">Strategy</th>
                          <th className="py-2 px-4 font-medium text-right">Benchmark</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/50">
                        <ComparisonRow label="Return" val1={backtestData.strategy.return} val2={backtestData.benchmark.return} isPct />
                        <ComparisonRow label="CAGR" val1={backtestData.strategy.cagr} val2={backtestData.benchmark.cagr} isPct />
                        <ComparisonRow label="Volatility" val1={backtestData.strategy.volatility} val2={backtestData.benchmark.volatility} isPct invertColor />
                        <ComparisonRow label="Sharpe" val1={backtestData.strategy.sharpe} val2={backtestData.benchmark.sharpe} />
                        <ComparisonRow label="Sortino" val1={backtestData.strategy.sortino} val2={backtestData.benchmark.sortino} />
                        <ComparisonRow label="Max DD" val1={backtestData.strategy.max_drawdown} val2={backtestData.benchmark.max_drawdown} isPct invertColor />
                        <ComparisonRow label="Calmar" val1={backtestData.strategy.calmar} val2={backtestData.benchmark.calmar} />
                        <ComparisonRow label="Exposure" val1={backtestData.strategy.exposure} val2={backtestData.benchmark.exposure} isPct />
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>

              <Card>
                <CardHeader className="py-3 flex flex-row items-center justify-between">
                  <CardTitle className="text-sm">Trade Log</CardTitle>
                  <button className="flex items-center gap-1 text-xs text-primary hover:text-primary-hover font-medium transition-colors">
                    <Download size={14} /> Export CSV
                  </button>
                </CardHeader>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left whitespace-nowrap">
                    <thead className="text-[10px] uppercase text-text-muted bg-surface-hover/50 border-b border-border">
                      <tr>
                        <th className="py-2.5 px-4 font-medium">Entry Date</th>
                        <th className="py-2.5 px-4 font-medium text-right">Entry Price</th>
                        <th className="py-2.5 px-4 font-medium">Exit Date</th>
                        <th className="py-2.5 px-4 font-medium text-right">Exit Price</th>
                        <th className="py-2.5 px-4 font-medium text-right">Units</th>
                        <th className="py-2.5 px-4 font-medium text-right">Fees</th>
                        <th className="py-2.5 px-4 font-medium text-right">P&L</th>
                        <th className="py-2.5 px-4 font-medium text-right">Return</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50">
                      {backtestData.trades.length === 0 ? (
                        <tr><td colSpan={8} className="py-8 text-center text-text-muted">No trades executed in this period</td></tr>
                      ) : (
                        backtestData.trades.map((t: Trade, i: number) => {
                          const ret = t.exit_price ? (t.exit_price - t.entry_price) / t.entry_price : 0;
                          return (
                            <tr key={i} className="hover:bg-surface-highlight/30 transition-colors">
                              <td className="py-2 px-4 font-mono text-xs">{t.entry_date}</td>
                              <td className="py-2 px-4 text-right font-mono text-xs">${t.entry_price.toFixed(2)}</td>
                              <td className="py-2 px-4 font-mono text-xs text-text-muted">{t.exit_date || 'OPEN'}</td>
                              <td className="py-2 px-4 text-right font-mono text-xs text-text-muted">{t.exit_price ? `$${t.exit_price.toFixed(2)}` : '-'}</td>
                              <td className="py-2 px-4 text-right font-mono text-xs">{t.units.toFixed(4)}</td>
                              <td className="py-2 px-4 text-right font-mono text-xs text-text-muted">${t.fees.toFixed(2)}</td>
                              <td className={`py-2 px-4 text-right font-mono text-xs font-medium ${((t.pnl ?? 0) >= 0) ? 'text-positive' : 'text-negative'}`}>
                                {t.pnl ? `$${t.pnl.toFixed(2)}` : '-'}
                              </td>
                              <td className={`py-2 px-4 text-right font-mono text-xs font-medium ${ret >= 0 ? 'text-positive' : 'text-negative'}`}>
                                {t.exit_price ? (ret > 0 ? '+' : '') + `${(ret * 100).toFixed(2)}%` : '-'}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </Card>

            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultMetric({ title, value, isNegative }: { title: string, value: string, isNegative?: boolean }) {
  return (
    <Card className="px-4 py-3 flex flex-col justify-center">
      <div className="text-[10px] uppercase font-bold tracking-wider text-text-muted mb-1 truncate">{title}</div>
      <div className={`text-xl font-mono font-bold tracking-tight ${isNegative ? 'text-negative' : 'text-text-main'}`}>
        {value}
      </div>
    </Card>
  );
}

function ComparisonRow({ label, val1, val2, isPct, invertColor }: { label: string, val1: number, val2: number, isPct?: boolean, invertColor?: boolean }) {
  const format = (v: number) => isPct ? `${(v * 100).toFixed(2)}%` : v.toFixed(2);
  let better = val1 > val2;
  if (invertColor) better = val1 < val2;
  const isDraw = Math.abs(val1 - val2) < 0.0001;

  return (
    <tr className="hover:bg-surface-highlight/30 transition-colors">
      <td className="py-2.5 px-4 text-text-muted">{label}</td>
      <td className={`py-2.5 px-4 text-right font-mono font-medium ${isDraw ? 'text-text-main' : (better ? 'text-positive' : 'text-negative')}`}>
        {format(val1)}
      </td>
      <td className="py-2.5 px-4 text-right font-mono text-text-muted">
        {format(val2)}
      </td>
    </tr>
  );
}
