import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { MarketAnalysisResponse } from '../api/types';
import Plot from 'react-plotly.js';
import { Activity, ArrowUpRight, ArrowDownRight, TrendingUp, TrendingDown, Layers, Database, AlertCircle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';

export function MarketAnalysis() {
  const [lookback, setLookback] = useState<string>('1Y');

  const { data, isLoading, isError, error } = useQuery<MarketAnalysisResponse>({
    queryKey: ['market-analysis', lookback],
    queryFn: async () => (await apiClient.get(`/market-analysis?lookback=${lookback}`)).data
  });

  const formatPct = (val: number) => `${(val * 100).toFixed(2)}%`;

  if (isLoading) {
    return (
      <div className="flex flex-col h-full space-y-6 animate-pulse">
        <div className="h-10 w-48 bg-surface-hover rounded-md"></div>
        <div className="h-24 bg-surface-hover rounded-xl"></div>
        <div className="h-[400px] bg-surface-hover rounded-xl"></div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col h-full items-center justify-center space-y-4 text-center">
        <AlertCircle size={48} className="text-negative" />
        <h2 className="text-xl font-bold text-negative">Unable to load market data</h2>
        <p className="text-text-muted max-w-md">{error instanceof Error ? error.message : "No historical market data available for the selected assets."}</p>
        <button onClick={() => window.location.reload()} className="btn-primary mt-4">Retry</button>
      </div>
    );
  }

  const chartTraces = Object.entries(data.chart_data).map(([asset, chart]) => ({
    x: chart.dates,
    y: chart.rebased,
    type: 'scatter' as const,
    mode: 'lines' as const,
    name: asset,
    line: { width: 1.5 }
  }));

  const adRatio = data.breadth.declining === 0 ? '∞' : (data.breadth.advancing / data.breadth.declining).toFixed(2);
  const advancingPct = formatPct(data.breadth.total > 0 ? data.breadth.advancing / data.breadth.total : 0);
  const decliningPct = formatPct(data.breadth.total > 0 ? data.breadth.declining / data.breadth.total : 0);

  return (
    <div className="flex flex-col space-y-6 animate-fade-in max-w-7xl mx-auto w-full pb-8">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Market Analysis</h1>
          <p className="text-sm text-text-muted mt-1">Macro-level overview of asset classes and cross-market indicators.</p>
        </div>
        <div className="flex items-center space-x-3 text-xs font-medium bg-surface-highlight/30 px-3 py-1.5 rounded-full border border-border">
          <Database size={14} className="text-primary" />
          <span className="text-text-muted">Data through:</span>
          <span className="text-text-main font-mono">{data.kpis.data_through}</span>
          <span className="text-border px-1">|</span>
          <span className="text-text-muted">Historical Data</span>
        </div>
      </div>

      {/* Top KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard title="Tracked Assets" value={data.kpis.tracked_assets.toString()} />
        <KpiCard title="Advancing" value={data.breadth.advancing.toString()} valueClass="text-positive" />
        <KpiCard title="Declining" value={data.breadth.declining.toString()} valueClass="text-negative" />
        <KpiCard title="Avg Return" value={formatPct(data.kpis.avg_return)} valueClass={data.kpis.avg_return >= 0 ? 'text-positive' : 'text-negative'} />
        <KpiCard title="Best Performer" value={data.kpis.best_performer} truncate />
        <KpiCard title="Worst Performer" value={data.kpis.worst_performer} truncate />
      </div>

      {/* Main Performance Chart */}
      <Card className="flex flex-col min-h-[450px]">
        <CardHeader className="py-3 border-b border-border/50 flex flex-row items-center justify-between">
          <CardTitle className="text-sm flex items-center">
            <Activity size={16} className="text-primary mr-2" /> 
            Normalized Market Performance
          </CardTitle>
          <div className="flex bg-surface-hover rounded-md p-1 space-x-1">
            {['1M', '3M', '6M', '1Y', 'MAX'].map(p => (
              <button
                key={p}
                onClick={() => setLookback(p)}
                className={`px-3 py-1 text-xs font-bold rounded-sm transition-colors ${lookback === p ? 'bg-surface shadow-sm text-primary' : 'text-text-muted hover:text-text-main'}`}
              >
                {p}
              </button>
            ))}
          </div>
        </CardHeader>
        <div className="flex-1 w-full p-2">
          {chartTraces.length > 0 ? (
            <Plot
              data={chartTraces}
              layout={{
                autosize: true,
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                margin: { t: 20, r: 20, l: 40, b: 30 },
                xaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true },
                yaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true },
                font: { color: 'var(--text-main)', family: 'Inter' },
                legend: { orientation: 'h', y: 1.05, x: 0 },
                hovermode: 'x unified',
                colorway: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#f97316']
              }}
              useResizeHandler={true}
              style={{ width: '100%', height: '100%' }}
              config={{ displayModeBar: false, responsive: true }}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-text-muted text-sm">
              Insufficient data for selected period.
            </div>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Market Breadth & Sectors */}
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader className="py-3 border-b border-border/50">
              <CardTitle className="text-sm">Market Breadth</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {data.breadth.total > 0 ? (
                <div className="p-5 space-y-6">
                  <div className="flex justify-between items-end">
                    <div>
                      <div className="text-[10px] uppercase font-bold text-text-muted mb-1">A/D Ratio</div>
                      <div className="text-3xl font-mono font-bold tracking-tight">{adRatio}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] uppercase font-bold text-text-muted mb-1">Unchanged</div>
                      <div className="text-xl font-mono font-medium text-text-muted">{data.breadth.unchanged}</div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="font-medium text-positive flex items-center"><ArrowUpRight size={14} className="mr-1"/> Advancing ({data.breadth.advancing})</span>
                        <span className="font-mono text-positive">{advancingPct}</span>
                      </div>
                      <div className="w-full bg-surface-hover rounded-full h-2 overflow-hidden">
                        <div className="bg-positive h-2 rounded-full" style={{ width: advancingPct }}></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="font-medium text-negative flex items-center"><ArrowDownRight size={14} className="mr-1"/> Declining ({data.breadth.declining})</span>
                        <span className="font-mono text-negative">{decliningPct}</span>
                      </div>
                      <div className="w-full bg-surface-hover rounded-full h-2 overflow-hidden">
                        <div className="bg-negative h-2 rounded-full" style={{ width: decliningPct }}></div>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-sm text-text-muted">Insufficient asset coverage for breadth analysis</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="py-3 border-b border-border/50">
              <CardTitle className="text-sm flex items-center">
                <Layers size={16} className="text-primary mr-2" /> Sector Performance
              </CardTitle>
            </CardHeader>
            <div className="p-0 overflow-hidden">
              <table className="w-full text-sm text-left">
                <thead className="text-[10px] uppercase text-text-muted bg-surface-hover/50 border-b border-border">
                  <tr>
                    <th className="py-2.5 px-4 font-medium">Asset Class</th>
                    <th className="py-2.5 px-4 font-medium text-right">Avg Return</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {Object.entries(data.sector_performance).length > 0 ? (
                    Object.entries(data.sector_performance)
                      .sort((a, b) => b[1] - a[1])
                      .map(([sector, ret]) => (
                      <tr key={sector} className="hover:bg-surface-highlight/30 transition-colors">
                        <td className="py-3 px-4 font-medium">{sector}</td>
                        <td className={`py-3 px-4 text-right font-mono font-medium flex items-center justify-end gap-1 ${ret >= 0 ? 'text-positive' : 'text-negative'}`}>
                          {ret >= 0 ? <TrendingUp size={14}/> : <TrendingDown size={14}/>}
                          {(ret * 100).toFixed(2)}%
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr><td colSpan={2} className="py-6 text-center text-text-muted text-xs">No sector metadata available</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Asset Universe Monitor */}
        <Card className="lg:col-span-2 flex flex-col h-full">
          <CardHeader className="py-3 border-b border-border/50">
            <CardTitle className="text-sm">Asset Universe Monitor</CardTitle>
          </CardHeader>
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-sm text-left whitespace-nowrap">
              <thead className="text-[10px] uppercase text-text-muted bg-surface-hover/50 border-b border-border sticky top-0">
                <tr>
                  <th className="py-3 px-4 font-medium">Asset</th>
                  <th className="py-3 px-4 font-medium">Class</th>
                  <th className="py-3 px-4 font-medium text-right">Latest Price</th>
                  <th className="py-3 px-4 font-medium text-right">Daily Return</th>
                  <th className="py-3 px-4 font-medium text-right">Period Return</th>
                  <th className="py-3 px-4 font-medium text-right">Volatility</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {data.monitor.map((asset) => (
                  <tr key={asset.symbol} className="hover:bg-surface-highlight/30 transition-colors">
                    <td className="py-2.5 px-4">
                      <div className="font-bold">{asset.symbol}</div>
                      <div className="text-xs text-text-muted">{asset.name}</div>
                    </td>
                    <td className="py-2.5 px-4">
                      <span className="text-[10px] font-bold tracking-wider px-2 py-1 rounded bg-surface-hover text-text-muted border border-border/50">
                        {asset.asset_class}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-text-main">${asset.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td className={`py-2.5 px-4 text-right font-mono font-medium ${asset.daily_return >= 0 ? 'text-positive' : 'text-negative'}`}>
                      {asset.daily_return > 0 ? '+' : ''}{formatPct(asset.daily_return)}
                    </td>
                    <td className={`py-2.5 px-4 text-right font-mono font-bold ${asset.period_return >= 0 ? 'text-positive' : 'text-negative'}`}>
                      {asset.period_return > 0 ? '+' : ''}{formatPct(asset.period_return)}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-text-muted">
                      {formatPct(asset.volatility)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

      </div>
    </div>
  );
}

function KpiCard({ title, value, valueClass = 'text-text-main', truncate }: { title: string, value: string, valueClass?: string, truncate?: boolean }) {
  return (
    <Card className="px-4 py-3 flex flex-col justify-center border-border/50 shadow-sm">
      <div className="text-[10px] uppercase font-bold tracking-wider text-text-muted mb-1 truncate">{title}</div>
      <div className={`text-xl font-mono font-bold tracking-tight ${valueClass} ${truncate ? 'truncate max-w-[120px]' : ''}`} title={value}>
        {value}
      </div>
    </Card>
  );
}
