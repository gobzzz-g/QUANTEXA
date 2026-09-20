import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { MarketAnalysisResponse } from '../api/types';
import Plot from 'react-plotly.js';
import {
  Activity, ArrowUpRight, ArrowDownRight, Database,
  AlertCircle, RefreshCw, ChevronDown, FileX, Loader2
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { useBatch } from '../contexts/BatchContext';
import { useNavigate } from 'react-router-dom';

interface BatchInfo {
  batch_id: string;
  batch_name: string;
  dataset_filename: string;
  status: string;
  created_at: string;
}

export function MarketAnalysis() {
  const navigate = useNavigate();
  const { selectedBatchId, setSelectedBatchId } = useBatch();
  const [lookback, setLookback] = useState<string>('1Y');

  // 1. Fetch all batches for the batch selector
  const { data: batchesResp, isLoading: batchesLoading } = useQuery({
    queryKey: ['fa-batches'],
    queryFn: async () => (await apiClient.get('/financial-agent/batches')).data,
    staleTime: 30_000,
  });
  const batches: BatchInfo[] = batchesResp?.batches ?? [];

  // Auto-select first batch if none selected
  const effectiveBatchId = selectedBatchId ?? (batches.length > 0 ? batches[0].batch_id : null);
  if (!selectedBatchId && batches.length > 0 && effectiveBatchId) {
    setSelectedBatchId(effectiveBatchId);
  }

  // 2. Fetch batch-scoped market analysis data
  const {
    data,
    isLoading: analysisLoading,
    isError,
    error,
    refetch,
  } = useQuery<MarketAnalysisResponse>({
    queryKey: ['market-analysis', effectiveBatchId, lookback],
    queryFn: async () =>
      (await apiClient.get(`/financial-agent/batch/${effectiveBatchId}/market-analysis?lookback=${lookback}`)).data,
    enabled: !!effectiveBatchId,
    staleTime: 30_000,
  });

  const isLoading = batchesLoading || analysisLoading;

  const formatPct = (val: number | null | undefined) => {
    if (val == null) return '—';
    return `${(val * 100).toFixed(2)}%`;
  };

  const formatSignedPct = (val: number | null | undefined) => {
    if (val == null) return '—';
    const prefix = val > 0 ? '+' : '';
    return `${prefix}${(val * 100).toFixed(2)}%`;
  };

  // ─── EMPTY STATE: No batches exist ──────────────────────────────────────────
  if (!batchesLoading && batches.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 animate-fade-in">
        <FileX size={56} className="text-text-muted opacity-40" />
        <div className="text-center">
          <h2 className="text-xl font-bold text-text-main mb-2">No analysis batches available</h2>
          <p className="text-text-muted text-sm mb-6">
            Upload a dataset in the Data &amp; Pipeline page to run market analysis.
          </p>
          <button
            onClick={() => navigate('/pipeline')}
            className="btn-primary px-6 py-2.5 rounded-full text-sm font-semibold"
          >
            Go to Data &amp; Pipeline
          </button>
        </div>
      </div>
    );
  }

  // ─── ERROR STATE ────────────────────────────────────────────────────────────
  if (isError && !isLoading) {
    return (
      <div className="flex flex-col h-full items-center justify-center space-y-4 text-center py-24">
        <AlertCircle size={48} className="text-negative" />
        <h2 className="text-xl font-bold text-text-main">Unable to load market analysis for this batch.</h2>
        <p className="text-text-muted max-w-md text-sm">
          {error instanceof Error ? error.message : 'No market data available for the selected batch.'}
        </p>
        <button
          onClick={() => refetch()}
          className="btn-secondary flex items-center gap-2 px-5 py-2 rounded-full text-sm mt-2"
        >
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );
  }

  // Chart traces from real batch data
  const chartTraces = data?.chart_data
    ? Object.entries(data.chart_data).map(([asset, chart]) => ({
        x: chart.dates,
        y: chart.rebased,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: chart.name || asset,
        line: { width: 2 },
      }))
    : [];

  const breadthTotal = data?.breadth?.total ?? 0;
  const advancingCount = data?.breadth?.advancing ?? 0;
  const decliningCount = data?.breadth?.declining ?? 0;
  const unchangedCount = data?.breadth?.unchanged ?? 0;
  const adRatioDisplay =
    data?.breadth?.ad_ratio ??
    (decliningCount === 0 ? (advancingCount > 0 ? '∞' : '0.00') : (advancingCount / decliningCount).toFixed(2));
  const advancingPct = breadthTotal > 0 ? (advancingCount / breadthTotal) * 100 : 0;
  const decliningPct = breadthTotal > 0 ? (decliningCount / breadthTotal) * 100 : 0;

  const avgPeriodReturn = data?.kpis?.avg_period_return ?? data?.kpis?.avg_return ?? 0;
  const highestPerformerName = data?.kpis?.highest_performer ?? data?.kpis?.best_performer ?? '—';
  const highestPerformerRet = data?.kpis?.highest_period_return;
  const lowestPerformerName = data?.kpis?.lowest_performer ?? data?.kpis?.worst_performer ?? '—';
  const lowestPerformerRet = data?.kpis?.lowest_period_return;

  return (
    <div className="flex flex-col space-y-6 animate-fade-in max-w-7xl mx-auto w-full pb-8 p-4 md:p-6">
      {/* ── HEADER ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-text-main">Market Analysis</h1>
          <p className="text-sm text-text-muted mt-1">
            Cross-asset performance, market breadth, and normalized comparative returns.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3">
          {/* Selected Batch Selector */}
          <div className="flex flex-col gap-1 min-w-[220px]">
            <label className="text-[10px] uppercase font-bold text-text-muted tracking-wider">
              Selected Batch
            </label>
            <div className="relative">
              <select
                value={effectiveBatchId ?? ''}
                onChange={e => setSelectedBatchId(e.target.value || null)}
                className="w-full appearance-none bg-surface border border-border rounded-lg px-3 py-2 pr-9 text-sm font-medium text-text-main focus:outline-none focus:border-primary cursor-pointer"
                disabled={batchesLoading}
              >
                {batchesLoading && <option value="">Loading batches…</option>}
                {batches.map(b => (
                  <option key={b.batch_id} value={b.batch_id}>
                    {b.batch_name || b.batch_id}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
              />
            </div>
          </div>

          {/* Data through meta badge */}
          {data?.kpis?.data_through && (
            <div className="flex items-center space-x-2 text-xs font-medium bg-surface-highlight/40 px-3.5 py-2.5 rounded-lg border border-border/80 self-stretch sm:self-auto justify-center">
              <Database size={14} className="text-primary" />
              <span className="text-text-muted">Data through:</span>
              <span className="text-text-main font-mono font-semibold">{data.kpis.data_through}</span>
            </div>
          )}
        </div>
      </div>

      {/* ── LOADING STATE ────────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="flex items-center justify-center gap-3 py-24 text-text-muted">
          <Loader2 size={28} className="animate-spin text-primary" />
          <span className="text-sm font-medium">Loading batch market analysis…</span>
        </div>
      )}

      {/* ── MAIN CONTENT ─────────────────────────────────────────────────────── */}
      {!isLoading && data && (
        <>
          {/* ── SUMMARY CARDS ─────────────────────────────────────────────────── */}
          <section>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
              <KpiCard
                title="Tracked Assets"
                value={(data.kpis.tracked_assets ?? 0).toString()}
                sub="Batch assets"
              />
              <KpiCard
                title="Advancing"
                value={advancingCount.toString()}
                valueClass="text-positive"
                sub="Daily return > 0"
              />
              <KpiCard
                title="Declining"
                value={decliningCount.toString()}
                valueClass={decliningCount > 0 ? 'text-negative' : 'text-text-muted'}
                sub="Daily return < 0"
              />
              <KpiCard
                title="Average Period Return"
                value={formatSignedPct(avgPeriodReturn)}
                valueClass={avgPeriodReturn >= 0 ? 'text-positive' : 'text-negative'}
                sub={`Selected ${lookback}`}
              />
              <KpiCard
                title="Highest Period Return"
                value={highestPerformerRet != null ? formatSignedPct(highestPerformerRet) : '—'}
                valueClass="text-positive"
                sub={highestPerformerName}
                truncate
              />
              <KpiCard
                title="Lowest Period Return"
                value={lowestPerformerRet != null ? formatSignedPct(lowestPerformerRet) : '—'}
                valueClass={lowestPerformerRet != null && lowestPerformerRet < 0 ? 'text-negative' : 'text-text-main'}
                sub={lowestPerformerName}
                truncate
              />
            </div>
          </section>

          {/* ── NORMALIZED MARKET PERFORMANCE CHART ───────────────────────────── */}
          <Card className="flex flex-col min-h-[460px] shadow-sm">
            <CardHeader className="py-3.5 border-b border-border/50 flex flex-row items-center justify-between">
              <CardTitle className="text-sm flex items-center">
                <Activity size={16} className="text-primary mr-2" />
                Normalized Market Performance
              </CardTitle>
              <div className="flex bg-surface-hover rounded-md p-1 space-x-1">
                {(['1M', '3M', '6M', '1Y', 'MAX'] as const).map(p => (
                  <button
                    key={p}
                    onClick={() => setLookback(p)}
                    className={`px-3 py-1 text-xs font-bold rounded-sm transition-colors ${
                      lookback === p
                        ? 'bg-surface shadow-sm text-primary'
                        : 'text-text-muted hover:text-text-main'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </CardHeader>
            <div className="flex-1 w-full p-2.5 min-h-[380px]">
              {chartTraces.length > 0 ? (
                <Plot
                  data={chartTraces}
                  layout={{
                    autosize: true,
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    margin: { t: 20, r: 20, l: 45, b: 35 },
                    xaxis: {
                      color: 'var(--text-muted)',
                      gridcolor: 'var(--border-color)',
                      showgrid: true,
                      tickfont: { family: 'Inter', size: 10 },
                    },
                    yaxis: {
                      color: 'var(--text-muted)',
                      gridcolor: 'var(--border-color)',
                      showgrid: true,
                      tickfont: { family: 'Inter', size: 10 },
                      title: { text: 'Rebased (100 = start)', font: { size: 10 } },
                    },
                    font: { color: 'var(--text-main)', family: 'Inter' },
                    legend: {
                      orientation: 'h',
                      yanchor: 'bottom',
                      y: 1.02,
                      xanchor: 'right',
                      x: 1,
                      font: { family: 'Inter', size: 11, color: 'var(--text-main)' },
                    },
                    hovermode: 'x unified',
                    colorway: ['#10b981', '#f59e0b', '#3b82f6', '#8b5cf6', '#ef4444', '#06b6d4', '#f97316'],
                  }}
                  useResizeHandler={true}
                  style={{ width: '100%', height: '100%' }}
                  config={{ displayModeBar: false, responsive: true }}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-text-muted text-sm py-20">
                  No price history available for the selected period.
                </div>
              )}
            </div>
          </Card>

          {/* ── LOWER SECTION: MARKET BREADTH & ASSET UNIVERSE MONITOR ─────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Market Breadth */}
            <Card className="flex flex-col shadow-sm">
              <CardHeader className="py-3.5 border-b border-border/50">
                <CardTitle className="text-sm">Market Breadth</CardTitle>
              </CardHeader>
              <CardContent className="p-5 flex-1 flex flex-col justify-between space-y-6">
                {breadthTotal > 0 ? (
                  <>
                    <div className="flex justify-between items-end">
                      <div>
                        <div className="text-[10px] uppercase font-bold text-text-muted mb-1">
                          A/D Ratio
                        </div>
                        <div className="text-3xl font-mono font-bold tracking-tight text-text-main">
                          {adRatioDisplay}
                        </div>
                        <div className="text-[11px] text-text-muted mt-0.5">
                          {decliningCount === 0 && advancingCount > 0 ? 'No declining assets' : 'Advancing / Declining'}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-[10px] uppercase font-bold text-text-muted mb-1">
                          Unchanged
                        </div>
                        <div className="text-2xl font-mono font-medium text-text-muted">
                          {unchangedCount}
                        </div>
                        <div className="text-[10px] text-text-muted">|Δ| ≤ 0.01%</div>
                      </div>
                    </div>

                    <div className="space-y-4 pt-2">
                      <div>
                        <div className="flex justify-between text-xs mb-1.5 font-medium">
                          <span className="text-positive flex items-center">
                            <ArrowUpRight size={14} className="mr-1" />
                            Advancing ({advancingCount})
                          </span>
                          <span className="font-mono text-positive">{advancingPct.toFixed(1)}%</span>
                        </div>
                        <div className="w-full bg-surface-hover rounded-full h-2.5 overflow-hidden">
                          <div
                            className="bg-positive h-2.5 rounded-full transition-all duration-500"
                            style={{ width: `${advancingPct}%` }}
                          />
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between text-xs mb-1.5 font-medium">
                          <span className="text-negative flex items-center">
                            <ArrowDownRight size={14} className="mr-1" />
                            Declining ({decliningCount})
                          </span>
                          <span className="font-mono text-negative">{decliningPct.toFixed(1)}%</span>
                        </div>
                        <div className="w-full bg-surface-hover rounded-full h-2.5 overflow-hidden">
                          <div
                            className="bg-negative h-2.5 rounded-full transition-all duration-500"
                            style={{ width: `${decliningPct}%` }}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="pt-2 text-[11px] text-text-muted border-t border-border/50">
                      Calculated from latest available daily returns across {breadthTotal} batch assets.
                    </div>
                  </>
                ) : (
                  <div className="p-8 text-center text-sm text-text-muted">
                    Insufficient asset coverage for breadth analysis
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Asset Universe Monitor */}
            <Card className="lg:col-span-2 flex flex-col shadow-sm">
              <CardHeader className="py-3.5 border-b border-border/50 flex flex-row items-center justify-between">
                <CardTitle className="text-sm">Asset Universe Monitor</CardTitle>
                <span className="text-[11px] font-mono text-text-muted">
                  {data.monitor.length} assets · {lookback} Period
                </span>
              </CardHeader>
              <div className="overflow-x-auto flex-1">
                {data.monitor.length === 0 ? (
                  <div className="p-8 text-center text-sm text-text-muted">
                    No assets found in selected batch.
                  </div>
                ) : (
                  <table className="w-full text-sm text-left whitespace-nowrap">
                    <thead className="text-[10px] uppercase text-text-muted bg-surface-hover/50 border-b border-border sticky top-0">
                      <tr>
                        <th className="py-3 px-4 font-medium">Asset</th>
                        <th className="py-3 px-4 font-medium">Class</th>
                        <th className="py-3 px-4 font-medium text-right">Latest Price</th>
                        <th className="py-3 px-4 font-medium text-right">Daily Return</th>
                        <th className="py-3 px-4 font-medium text-right">{lookback} Period Return</th>
                        <th className="py-3 px-4 font-medium text-right">Annualized Volatility</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50">
                      {data.monitor.map(asset => {
                        const isDailyPos = asset.daily_return >= 0;
                        const isPeriodPos = asset.period_return >= 0;
                        return (
                          <tr
                            key={asset.symbol}
                            className="hover:bg-surface-highlight/30 transition-colors cursor-pointer"
                            onClick={() => navigate('/explorer', { state: { asset: asset.symbol } })}
                          >
                            <td className="py-3 px-4">
                              <div className="font-bold text-text-main">{asset.symbol}</div>
                              <div className="text-xs text-text-muted">{asset.name}</div>
                            </td>
                            <td className="py-3 px-4">
                              <span className="text-[10px] font-bold tracking-wider px-2 py-0.5 rounded bg-surface-hover text-text-muted border border-border/50">
                                {asset.asset_class}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-semibold text-text-main">
                              ${asset.current_price.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </td>
                            <td
                              className={`py-3 px-4 text-right font-mono font-medium ${
                                isDailyPos ? 'text-positive' : 'text-negative'
                              }`}
                            >
                              {formatSignedPct(asset.daily_return)}
                            </td>
                            <td
                              className={`py-3 px-4 text-right font-mono font-bold ${
                                isPeriodPos ? 'text-positive' : 'text-negative'
                              }`}
                            >
                              {formatSignedPct(asset.period_return)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-text-muted">
                              {formatPct(asset.volatility)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function KpiCard({
  title,
  value,
  valueClass = 'text-text-main',
  sub,
  truncate,
}: {
  title: string;
  value: string;
  valueClass?: string;
  sub?: string;
  truncate?: boolean;
}) {
  return (
    <Card className="px-4 py-3 flex flex-col justify-between border-border/50 shadow-sm min-h-[90px]">
      <div className="text-[10px] uppercase font-bold tracking-wider text-text-muted truncate">
        {title}
      </div>
      <div
        className={`text-xl font-mono font-bold tracking-tight ${valueClass} ${
          truncate ? 'truncate max-w-[140px]' : ''
        }`}
        title={value}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[11px] text-text-muted truncate font-medium mt-0.5" title={sub}>
          {sub}
        </div>
      )}
    </Card>
  );
}
