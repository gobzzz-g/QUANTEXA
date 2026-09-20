import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import Plot from 'react-plotly.js';
import {
  ShieldCheck, Database, Calendar, TrendingUp,
  ArrowUpRight, ArrowDownRight, LayoutGrid, Network,
  ChevronDown, AlertCircle, Loader2, FileX, RefreshCw,
  Layers, BarChart2
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { Badge } from '../components/Badge';
import { useNavigate } from 'react-router-dom';
import { useBatch } from '../contexts/BatchContext';

// ─── helpers ────────────────────────────────────────────────────────────────
const pct = (v: number | null | undefined, decimals = 2) =>
  v == null ? '—' : `${(v * 100).toFixed(decimals)}%`;

const fmt = (v: number | null | undefined, decimals = 2) =>
  v == null ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const statusColor: Record<string, string> = {
  COMPLETED: 'text-positive',
  RUNNING:   'text-warning',
  CREATED:   'text-primary',
  FAILED:    'text-negative',
  UNKNOWN:   'text-text-muted',
};

const REGIME_LABELS: Record<string, string> = {
  BULL_LOW_VOL:  '🟢 Bull · Low Vol',
  BULL_HIGH_VOL: '🟡 Bull · High Vol',
  BEAR_LOW_VOL:  '🔵 Bear · Low Vol',
  BEAR_HIGH_VOL: '🔴 Bear · High Vol',
  UNKNOWN:       '⬜ Unknown',
};

// ─── types ───────────────────────────────────────────────────────────────────
interface BatchInfo {
  batch_id: string;
  batch_name: string;
  dataset_filename: string;
  status: string;
  created_at: string;
}

interface AssetRecord {
  asset_id: string;
  symbol: string;
  name: string;
  asset_type: string;
}

interface StatRecord {
  symbol: string;
  name: string;
  asset_type: string;
  annualized_return: number;
  annualized_volatility: number;
  sharpe_ratio: number;
  max_drawdown: number;
  start_date: string;
  end_date: string;
}

interface OverviewData {
  batch_info: BatchInfo;
  assets: AssetRecord[];
  statistics: StatRecord[];
  latest_prices: Record<string, { close: number; date: string }>;
  latest_regime: Record<string, { regime: string; trend_state: string; volatility_state: string; date: string }>;
  correlations: Array<{ asset_1: string; asset_2: string; correlation: number; window_days: number; date: string }>;
  data_quality: {
    source: string;
    earliest_record: string | null;
    latest_record: string | null;
    tracked_assets: number;
    total_price_records: number;
    batch_status: string;
    dataset_filename: string;
  };
}

interface PriceData {
  batch_id: string;
  series: Record<string, { name: string; dates: string[]; closes: number[]; rebased: number[] }>;
}

// ─── component ───────────────────────────────────────────────────────────────
export function Overview() {
  const navigate = useNavigate();
  const { selectedBatchId, setSelectedBatchId } = useBatch();
  const [chartPeriod, setChartPeriod] = useState<string>('1Y');

  // 1. Fetch all batches for the selector
  const { data: batchesResp, isLoading: batchesLoading } = useQuery({
    queryKey: ['fa-batches'],
    queryFn: async () => (await apiClient.get('/financial-agent/batches')).data,
    staleTime: 30_000,
  });
  const batches: BatchInfo[] = batchesResp?.batches ?? [];

  // Auto-select first batch when list loads and nothing is selected
  const effectiveBatchId = selectedBatchId ?? (batches.length > 0 ? batches[0].batch_id : null);
  if (!selectedBatchId && batches.length > 0 && effectiveBatchId) {
    setSelectedBatchId(effectiveBatchId);
  }

  // 2. Fetch batch-scoped overview data
  const {
    data: overviewData,
    isLoading: overviewLoading,
    error: overviewError,
  } = useQuery<OverviewData>({
    queryKey: ['batch-overview', effectiveBatchId],
    queryFn: async () =>
      (await apiClient.get(`/financial-agent/batch/${effectiveBatchId}/overview-data`)).data,
    enabled: !!effectiveBatchId,
    staleTime: 60_000,
  });

  // 3. Fetch price series for the Relative Performance chart
  const { data: priceData, isLoading: pricesLoading } = useQuery<PriceData>({
    queryKey: ['batch-prices', effectiveBatchId],
    queryFn: async () =>
      (await apiClient.get(`/financial-agent/batch/${effectiveBatchId}/prices`)).data,
    enabled: !!effectiveBatchId,
    staleTime: 120_000,
  });

  const isLoading = batchesLoading || overviewLoading || pricesLoading;

  // ─── Derived: Relative Performance chart traces ───────────────────────────
  const chartData = useMemo(() => {
    if (!priceData?.series) return [];
    const series = priceData.series;
    const symbols = Object.keys(series);
    if (!symbols.length) return [];

    let cutoffStr = '1900-01-01';
    const allDates = Object.values(series)
      .flatMap(s => s.dates)
      .sort();
    const latestDateStr = allDates[allDates.length - 1] ?? '';

    if (latestDateStr) {
      const latest = new Date(latestDateStr);
      const cutoff = new Date(latest);
      if (chartPeriod === '1M') cutoff.setMonth(cutoff.getMonth() - 1);
      else if (chartPeriod === '3M') cutoff.setMonth(cutoff.getMonth() - 3);
      else if (chartPeriod === '6M') cutoff.setMonth(cutoff.getMonth() - 6);
      else if (chartPeriod === '1Y') cutoff.setFullYear(cutoff.getFullYear() - 1);
      else if (chartPeriod === 'MAX') cutoff.setFullYear(1900);
      cutoffStr = cutoff.toISOString().split('T')[0];
    }

    return symbols.map(sym => {
      const s = series[sym];
      const startIdx = s.dates.findIndex(d => d >= cutoffStr);
      const idx = startIdx === -1 ? 0 : startIdx;
      const filteredDates = s.dates.slice(idx);
      const base = s.rebased[idx] || 1;
      const filteredRebased = s.rebased.slice(idx).map(v => (v / base) * 100);
      return {
        x: filteredDates,
        y: filteredRebased,
        type: 'scatter',
        mode: 'lines',
        name: s.name || sym,
        line: { width: 2 },
      };
    });
  }, [priceData, chartPeriod]);

  // ─── Derived: Risk / Return scatter ──────────────────────────────────────
  const scatterData = useMemo(() => {
    const stats = overviewData?.statistics ?? [];
    if (!stats.length) return [];
    return [{
      x: stats.map(s => s.annualized_volatility * 100),
      y: stats.map(s => s.annualized_return * 100),
      text: stats.map(s => s.symbol),
      mode: 'markers+text',
      type: 'scatter',
      textposition: 'top center',
      marker: { size: 12, color: '#089958', line: { width: 1, color: '#067A46' } },
      hoverinfo: 'text+x+y',
    }];
  }, [overviewData]);

  // ─── Derived: Correlation matrix cells ───────────────────────────────────
  const correlationGrid = useMemo(() => {
    const corrs = overviewData?.correlations ?? [];
    const assets = overviewData?.assets ?? [];
    if (!corrs.length || assets.length < 2) return null;

    const symbols = assets.map(a => a.symbol);
    const map: Record<string, number> = {};
    corrs.forEach(c => {
      map[`${c.asset_1}|${c.asset_2}`] = c.correlation;
      map[`${c.asset_2}|${c.asset_1}`] = c.correlation;
    });

    return { symbols, map };
  }, [overviewData]);

  // ─── Selected batch info ──────────────────────────────────────────────────
  const batchInfo = overviewData?.batch_info;
  const dataQuality = overviewData?.data_quality;

  // ─── Helpers ──────────────────────────────────────────────────────────────
  const corrColor = (v: number) => {
    if (v >= 0.7) return 'bg-positive/20 text-positive';
    if (v >= 0.3) return 'bg-warning/10 text-warning';
    if (v >= -0.3) return 'bg-surface-hover text-text-muted';
    if (v >= -0.7) return 'bg-primary/10 text-primary';
    return 'bg-negative/20 text-negative';
  };

  // ─── EMPTY STATE: No batch selected ──────────────────────────────────────
  if (!batchesLoading && batches.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 animate-fade-in">
        <FileX size={56} className="text-text-muted opacity-40" />
        <div className="text-center">
          <h2 className="text-xl font-bold text-text-main mb-2">No analysis batches available</h2>
          <p className="text-text-muted text-sm mb-6">
            Upload a dataset in the Data &amp; Pipeline page to create your first batch.
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

  return (
    <div className="space-y-8 animate-fade-in p-4 md:p-8 max-w-[1600px] mx-auto">

      {/* ── HEADER ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end border-b border-border pb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-text-main">
            Quantitative Market Intelligence
          </h1>
          <p className="text-sm text-text-muted mt-1 max-w-xl">
            Batch-scoped performance, risk metrics, and market structure analysis.
          </p>
        </div>

        {/* Batch Selector */}
        <div className="flex flex-col gap-2 min-w-[260px]">
          <label className="text-[10px] uppercase font-bold text-text-muted tracking-wider">
            Analysis Batch
          </label>
          <div className="relative">
            <select
              value={effectiveBatchId ?? ''}
              onChange={e => setSelectedBatchId(e.target.value || null)}
              className="w-full appearance-none bg-surface border border-border rounded-lg px-4 py-2.5 pr-10 text-sm font-medium text-text-main focus:outline-none focus:border-primary cursor-pointer"
              disabled={batchesLoading}
            >
              {batchesLoading && <option value="">Loading batches…</option>}
              {batches.map(b => (
                <option key={b.batch_id} value={b.batch_id}>
                  {b.batch_name || b.batch_id}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
          </div>

          {/* Batch meta row */}
          {batchInfo && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] font-mono text-text-muted">
              <span>
                <Database size={10} className="inline mr-1 text-primary" />
                {batchInfo.dataset_filename || '—'}
              </span>
              <span className={statusColor[batchInfo.status] ?? 'text-text-muted'}>
                ● {batchInfo.status}
              </span>
              {dataQuality?.tracked_assets != null && (
                <span>{dataQuality.tracked_assets} assets</span>
              )}
              {dataQuality?.latest_record && (
                <span>
                  <Calendar size={10} className="inline mr-1 text-primary" />
                  Data through: {dataQuality.latest_record}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── LOADING ──────────────────────────────────────────────────────────── */}
      {isLoading && effectiveBatchId && (
        <div className="flex items-center justify-center gap-3 py-24 text-text-muted">
          <Loader2 size={28} className="animate-spin text-primary" />
          <span className="text-sm font-medium">Loading batch data…</span>
        </div>
      )}

      {/* ── ERROR ────────────────────────────────────────────────────────────── */}
      {overviewError && !isLoading && (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <AlertCircle size={40} className="text-negative" />
          <div className="text-center">
            <p className="font-semibold text-text-main">Unable to load analysis data for this batch.</p>
            <p className="text-sm text-text-muted mt-1">{String(overviewError)}</p>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="btn-secondary flex items-center gap-2 px-5 py-2 rounded-full text-sm"
          >
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      )}

      {/* ── MAIN CONTENT (only when data loaded) ─────────────────────────────── */}
      {overviewData && !isLoading && !overviewError && (
        <>
          {/* ── ASSET SUMMARY CARDS ──────────────────────────────────────── */}
          <section>
            <h2 className="text-[11px] uppercase font-bold text-text-muted tracking-wider mb-4">
              Asset Summary · Layer 2 Statistics
            </h2>
            {overviewData.statistics.length === 0 ? (
              <div className="text-sm text-text-muted py-8 text-center border border-border rounded-lg">
                No Layer 2 statistics available for this batch yet.
                <br />
                <span className="text-xs">Run the pipeline to generate quantitative metrics.</span>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
                {overviewData.statistics.map(stat => {
                  const latestPrice = overviewData.latest_prices[stat.symbol];
                  const isPos = stat.annualized_return >= 0;
                  return (
                    <Card
                      key={stat.symbol}
                      className="hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden relative group"
                      onClick={() => navigate('/explorer', { state: { asset: stat.symbol } })}
                    >
                      <div className={`absolute top-0 left-0 w-full h-0.5 ${isPos ? 'bg-positive' : 'bg-negative'}`} />
                      <CardContent className="p-5">
                        <div className="flex justify-between items-start mb-3">
                          <div>
                            <h3 className="text-sm font-bold text-text-main">{stat.name}</h3>
                            <div className="text-[10px] uppercase font-bold text-text-muted tracking-wider mt-0.5">
                              {stat.symbol} · {stat.asset_type}
                            </div>
                          </div>
                          <div className={`p-1.5 rounded-full ${isPos ? 'bg-positive/10 text-positive' : 'bg-negative/10 text-negative'}`}>
                            {isPos ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
                          </div>
                        </div>

                        {latestPrice && (
                          <div className="text-2xl font-mono font-bold tracking-tight mb-3">
                            {fmt(latestPrice.close)}
                          </div>
                        )}

                        <div className="grid grid-cols-2 gap-y-2.5 gap-x-2 text-xs">
                          <div>
                            <div className="text-text-muted mb-0.5 text-[10px] uppercase font-bold tracking-wider">Ann. Return</div>
                            <div className={`font-mono font-semibold ${isPos ? 'text-positive' : 'text-negative'}`}>
                              {pct(stat.annualized_return)}
                            </div>
                          </div>
                          <div>
                            <div className="text-text-muted mb-0.5 text-[10px] uppercase font-bold tracking-wider">Sharpe Ratio</div>
                            <div className="font-mono font-semibold">{fmt(stat.sharpe_ratio)}</div>
                          </div>
                          <div>
                            <div className="text-text-muted mb-0.5 text-[10px] uppercase font-bold tracking-wider">Ann. Volatility</div>
                            <div className="font-mono font-semibold">{pct(stat.annualized_volatility)}</div>
                          </div>
                          <div>
                            <div className="text-text-muted mb-0.5 text-[10px] uppercase font-bold tracking-wider">Max Drawdown</div>
                            <div className="font-mono font-semibold text-negative">{pct(stat.max_drawdown)}</div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </section>

          {/* ── RELATIVE PERFORMANCE + MARKET REGIME ────────────────────── */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

            {/* Relative Performance Chart */}
            <Card className="xl:col-span-2 min-h-[420px] flex flex-col shadow-sm">
              <CardHeader className="flex flex-row items-center justify-between py-4 border-b border-border/50">
                <CardTitle className="text-sm flex items-center">
                  <TrendingUp size={16} className="text-primary mr-2" />
                  Relative Performance
                </CardTitle>
                <div className="flex gap-1 bg-surface-highlight/50 p-1 rounded-md">
                  {(['1M', '3M', '6M', '1Y', 'MAX'] as const).map(p => (
                    <button
                      key={p}
                      onClick={() => setChartPeriod(p)}
                      className={`px-3 py-1 text-xs font-bold rounded transition-colors ${
                        chartPeriod === p
                          ? 'bg-surface shadow-sm text-primary'
                          : 'text-text-muted hover:text-text-main'
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </CardHeader>
              <div className="flex-1 w-full p-2 min-h-[340px]">
                {pricesLoading ? (
                  <div className="flex items-center justify-center h-full">
                    <Loader2 size={24} className="animate-spin text-primary" />
                  </div>
                ) : chartData.length > 0 ? (
                  <Plot
                    data={chartData as any}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 20, r: 20, l: 45, b: 40 },
                      xaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true, tickfont: { family: 'Inter', size: 10 } },
                      yaxis: {
                        color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true,
                        tickfont: { family: 'Inter', size: 10 },
                        tickformat: '.0f', ticksuffix: '',
                        title: { text: 'Rebased (100 = start)', font: { size: 10 } }
                      },
                      legend: { orientation: 'h', yanchor: 'bottom', y: 1.02, xanchor: 'right', x: 1, font: { family: 'Inter', size: 10, color: 'var(--text-main)' } },
                      hovermode: 'x unified',
                    }}
                    useResizeHandler
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                ) : (
                  <div className="flex items-center justify-center h-full text-text-muted text-sm">
                    No price data available for this batch.
                  </div>
                )}
              </div>
            </Card>

            {/* Market Regime */}
            <Card className="shadow-sm flex flex-col">
              <CardHeader className="py-4 border-b border-border/50">
                <CardTitle className="text-sm flex items-center">
                  <Layers size={16} className="text-primary mr-2" />
                  Market Regime · Layer 5
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 flex-1">
                {Object.keys(overviewData.latest_regime).length === 0 ? (
                  <div className="text-sm text-text-muted text-center py-8">
                    Not available
                    <br />
                    <span className="text-xs">Run Layers 1–5 to generate regime data.</span>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(overviewData.latest_regime).map(([sym, regime]) => (
                      <div key={sym} className="p-3 rounded-lg bg-surface-hover border border-border/50">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-xs font-bold text-text-main">{sym}</span>
                          <span className="text-[10px] text-text-muted">{regime.date}</span>
                        </div>
                        <div className="text-xs font-mono">
                          {REGIME_LABELS[regime.regime] ?? regime.regime}
                        </div>
                        <div className="flex gap-2 mt-2">
                          <Badge variant={regime.trend_state === 'BULL' ? 'positive' : (regime.trend_state === 'BEAR' ? 'negative' : 'default')} className="text-[9px] px-2 py-0.5">
                            {regime.trend_state}
                          </Badge>
                          <Badge variant={regime.volatility_state === 'HIGH_VOLATILITY' ? 'warning' : 'default'} className="text-[9px] px-2 py-0.5">
                            {regime.volatility_state}
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* ── RISK/RETURN MAP + CORRELATION ──────────────────────────── */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

            {/* Risk / Return Map */}
            <Card className="min-h-[360px] flex flex-col shadow-sm">
              <CardHeader className="py-4 border-b border-border/50">
                <CardTitle className="text-sm flex items-center">
                  <LayoutGrid size={16} className="text-primary mr-2" />
                  Risk / Return Map
                </CardTitle>
              </CardHeader>
              <div className="flex-1 w-full p-2 min-h-[300px]">
                {scatterData.length > 0 ? (
                  <Plot
                    data={scatterData as any}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 30, r: 30, l: 50, b: 45 },
                      xaxis: {
                        title: { text: 'Annualized Volatility (%)', font: { size: 10 } },
                        color: 'var(--text-muted)', gridcolor: 'var(--border-color)',
                        showgrid: true, tickfont: { family: 'Inter', size: 10 },
                      },
                      yaxis: {
                        title: { text: 'Annualized Return (%)', font: { size: 10 } },
                        color: 'var(--text-muted)', gridcolor: 'var(--border-color)',
                        showgrid: true, tickfont: { family: 'Inter', size: 10 },
                      },
                      hovermode: 'closest',
                    }}
                    useResizeHandler
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                ) : (
                  <div className="flex items-center justify-center h-full text-text-muted text-sm">
                    No statistics data for this batch.
                  </div>
                )}
              </div>
            </Card>

            {/* Correlation Snapshot */}
            <Card className="shadow-sm flex flex-col">
              <CardHeader className="py-4 border-b border-border/50 flex flex-row items-center justify-between">
                <CardTitle className="text-sm flex items-center">
                  <Network size={16} className="text-primary mr-2" />
                  Correlation Snapshot · 90-day
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 flex-1">
                {!correlationGrid ? (
                  <div className="flex flex-col items-center justify-center h-full gap-4 py-8">
                    <BarChart2 size={32} className="text-border" />
                    <p className="text-sm text-text-muted text-center max-w-[220px]">
                      Correlation data not yet available for this batch.
                    </p>
                    <button
                      onClick={() => navigate('/correlation')}
                      className="btn-secondary text-xs py-2 px-4 rounded-full"
                    >
                      View Full Correlation Analysis
                    </button>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    {/* Header row */}
                    <div
                      className="grid gap-1 text-[10px] font-bold text-text-muted uppercase text-center mb-1"
                      style={{ gridTemplateColumns: `80px repeat(${correlationGrid.symbols.length}, 1fr)` }}
                    >
                      <div />
                      {correlationGrid.symbols.map(s => (
                        <div key={s} className="truncate px-1">{s}</div>
                      ))}
                    </div>
                    {/* Matrix rows */}
                    {correlationGrid.symbols.map(row => (
                      <div
                        key={row}
                        className="grid gap-1 mb-1"
                        style={{ gridTemplateColumns: `80px repeat(${correlationGrid.symbols.length}, 1fr)` }}
                      >
                        <div className="text-[10px] font-bold text-text-muted flex items-center truncate">{row}</div>
                        {correlationGrid.symbols.map(col => {
                          const v = row === col ? 1 : (correlationGrid.map[`${row}|${col}`] ?? null);
                          return (
                            <div
                              key={col}
                              className={`text-center text-[11px] font-mono py-2 rounded ${
                                row === col ? 'bg-primary/20 text-primary font-bold' : corrColor(v ?? 0)
                              }`}
                            >
                              {v == null ? '—' : v.toFixed(2)}
                            </div>
                          );
                        })}
                      </div>
                    ))}
                    <div className="mt-4">
                      <button
                        onClick={() => navigate('/correlation')}
                        className="btn-secondary w-full text-xs py-2 rounded-full"
                      >
                        View Full Correlation Analysis
                      </button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* ── DATA QUALITY ─────────────────────────────────────────────── */}
          {dataQuality && (
            <Card className="shadow-sm">
              <CardHeader className="py-3 border-b border-border/50">
                <CardTitle className="text-sm flex items-center">
                  <ShieldCheck size={16} className="text-primary mr-2" />
                  Data Quality
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                  <div>
                    <div className="text-text-muted text-[10px] uppercase font-bold tracking-wider mb-1">Source Database</div>
                    <Badge variant="outline" className="font-mono text-[10px] border-border bg-surface">{dataQuality.source}</Badge>
                  </div>
                  <div>
                    <div className="text-text-muted text-[10px] uppercase font-bold tracking-wider mb-1">Earliest Record</div>
                    <span className="font-mono text-text-main font-medium">{dataQuality.earliest_record ?? '—'}</span>
                  </div>
                  <div>
                    <div className="text-text-muted text-[10px] uppercase font-bold tracking-wider mb-1">Latest Record</div>
                    <span className="font-mono text-text-main font-medium">{dataQuality.latest_record ?? '—'}</span>
                  </div>
                  <div>
                    <div className="text-text-muted text-[10px] uppercase font-bold tracking-wider mb-1">Tracked Assets</div>
                    <span className="font-mono text-text-main font-bold text-base">{dataQuality.tracked_assets}</span>
                  </div>
                  <div>
                    <div className="text-text-muted text-[10px] uppercase font-bold tracking-wider mb-1">Total Price Records</div>
                    <span className="font-mono text-text-main font-medium">{dataQuality.total_price_records.toLocaleString()}</span>
                  </div>
                  <div>
                    <div className="text-text-muted text-[10px] uppercase font-bold tracking-wider mb-1">Dataset File</div>
                    <span className="font-mono text-text-main font-medium truncate block max-w-[180px]" title={dataQuality.dataset_filename}>
                      {dataQuality.dataset_filename}
                    </span>
                  </div>
                  <div>
                    <div className="text-text-muted text-[10px] uppercase font-bold tracking-wider mb-1">Batch Status</div>
                    <Badge
                      variant={dataQuality.batch_status === 'COMPLETED' ? 'positive' : (dataQuality.batch_status === 'FAILED' ? 'negative' : 'warning')}
                      className="text-[10px]"
                    >
                      {dataQuality.batch_status}
                    </Badge>
                  </div>
                  <div>
                    <div className="text-text-muted text-[10px] uppercase font-bold tracking-wider mb-1">System Health</div>
                    <Badge variant="positive" className="text-[10px]">OPERATIONAL</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
