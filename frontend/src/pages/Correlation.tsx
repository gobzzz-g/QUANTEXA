import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { CorrelationResponse } from '../api/types';
import Plot from 'react-plotly.js';
import {
  Grid, Info, Activity, ChevronDown, Calendar,
  ArrowUpRight, Loader2, Layers, AlertCircle, RefreshCw
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { Badge } from '../components/Badge';
import { useBatch } from '../contexts/BatchContext';

// ─── helpers ────────────────────────────────────────────────────────────────
const pct = (v: number | null | undefined, decimals = 2) =>
  v == null ? '—' : `${(v * 100).toFixed(decimals)}%`;

const fmt = (v: number | null | undefined, decimals = 2) =>
  v == null ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const SERIES_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4'];

interface BatchInfo {
  batch_id: string;
  batch_name: string;
  status?: string;
  dataset_filename?: string;
}

export function Correlation() {
  const navigate = useNavigate();
  const { selectedBatchId, setSelectedBatchId } = useBatch();
  const [showCovariance, setShowCovariance] = useState(false);

  // 1. Fetch batches list for batch selector
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

  // 2. Fetch batch-scoped correlation & risk data
  const {
    data: correlation,
    isLoading: correlationLoading,
    error: correlationError,
    refetch
  } = useQuery<CorrelationResponse>({
    queryKey: ['batch-correlation', effectiveBatchId],
    queryFn: async () => (await apiClient.get(`/correlation?batch_id=${effectiveBatchId}`)).data,
    enabled: !!effectiveBatchId,
    staleTime: 30_000,
  });

  const isLoading = batchesLoading || correlationLoading;

  // Batch isolation guard: ensure received data matches current effective batch
  const isDataMatchingBatch = !correlation || !effectiveBatchId || correlation.batch_id === effectiveBatchId;

  // Annotations for heatmap to display numerical values inside cells
  const heatmapAnnotations = useMemo(() => {
    if (!correlation?.matrix || !correlation?.assets) return [];
    const ann: any[] = [];
    correlation.assets.forEach((yAsset, rowIdx) => {
      correlation.assets.forEach((xAsset, colIdx) => {
        const val = correlation.matrix[rowIdx]?.[colIdx];
        if (typeof val === 'number') {
          ann.push({
            x: xAsset,
            y: yAsset,
            text: val.toFixed(2),
            font: {
              family: 'Inter, sans-serif',
              size: 13,
              color: '#ffffff',
              weight: 600,
            },
            showarrow: false,
          });
        }
      });
    });
    return ann;
  }, [correlation]);

  // Rolling correlation traces
  const rollingTraces = useMemo(() => {
    const series = correlation?.rolling_series ?? [];
    if (!series.length) return [];

    return series.map((s, idx) => ({
      x: s.dates,
      y: s.correlations,
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: s.pair,
      line: {
        color: SERIES_COLORS[idx % SERIES_COLORS.length],
        width: 2.2,
      },
      hovertemplate: `<b>${s.pair}</b><br>Date: %{x}<br>Correlation: %{y:.2f}<extra></extra>`,
    }));
  }, [correlation]);

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in max-w-7xl mx-auto w-full pb-8 p-4 md:p-6">
      {/* ── HEADER ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-text-main">
            Correlation & Risk
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Cross-asset dependencies and portfolio diversification metrics.
          </p>
        </div>

        {/* Batch Selector & Metadata */}
        <div className="flex flex-col gap-2 min-w-[220px] w-full sm:w-auto">
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

          <div className="flex items-center gap-3 text-[11px] font-mono text-text-muted">
            {correlation?.data_through && (
              <span className="flex items-center">
                <Calendar size={11} className="mr-1 text-primary" />
                Data through: {correlation.data_through}
              </span>
            )}
            {correlation?.assets && (
              <span className="text-text-muted">
                {correlation.assets.length} assets
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── MAIN CONTENT STATE HANDLING ────────────────────────────────────── */}
      {(() => {
        if (isLoading || !isDataMatchingBatch) {
          return (
            <div className="flex flex-col items-center justify-center min-h-[400px] gap-3">
              <Loader2 className="animate-spin text-primary" size={32} />
              <p className="text-sm text-text-muted">Loading correlation analysis for batch...</p>
            </div>
          );
        }

        if (!effectiveBatchId) {
          return (
            <div className="flex flex-col items-center justify-center min-h-[300px] gap-3 text-center border border-dashed border-border rounded-xl p-8">
              <AlertCircle size={36} className="text-text-muted" />
              <p className="text-base font-medium text-text-main">No analysis batch selected.</p>
              <p className="text-sm text-text-muted">Select a batch from the dropdown above to view correlation analysis.</p>
            </div>
          );
        }

        if (correlationError || !correlation) {
          return (
            <div className="flex flex-col items-center justify-center min-h-[300px] gap-3 text-center border border-border rounded-xl p-8 bg-surface">
              <AlertCircle size={36} className="text-negative" />
              <p className="text-base font-semibold text-text-main">Unable to load correlation analysis for this batch.</p>
              <button
                onClick={() => refetch()}
                className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-surface-highlight border border-border text-xs text-text-main hover:bg-border transition-colors mt-2"
              >
                <RefreshCw size={13} />
                Retry
              </button>
            </div>
          );
        }

        if (correlation.error || !correlation.assets || correlation.assets.length < 2) {
          return (
            <div className="flex flex-col items-center justify-center min-h-[300px] gap-3 text-center border border-dashed border-border rounded-xl p-8 bg-surface/50">
              <AlertCircle size={36} className="text-warning" />
              <p className="text-base font-medium text-text-main">
                {correlation.error || 'At least two assets are required for correlation analysis.'}
              </p>
              <p className="text-xs text-text-muted">
                The selected batch ({effectiveBatchId}) currently has {correlation.assets?.length ?? 0} assets.
              </p>
            </div>
          );
        }

        const data = correlation;
        return (
          <div className="space-y-6">
          {/* ── TOP ROW: CORRELATION MATRIX & DIVERSIFICATION EXPLANATION ───── */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Correlation Matrix Card */}
            <Card className="lg:col-span-3 flex flex-col min-h-[520px]">
              <CardHeader className="py-3 flex flex-row items-center justify-between">
                <CardTitle className="text-sm flex items-center">
                  <Grid size={16} className="text-primary mr-2" />
                  Cross-Asset Correlation Matrix
                </CardTitle>
                <Badge variant="outline" className="text-[11px] font-mono">
                  {data.window || 'Full Period'}
                </Badge>
              </CardHeader>
              <div className="flex-1 w-full relative p-2 min-h-[440px]">
                <Plot
                  data={[
                    {
                      z: data.matrix,
                      x: data.assets,
                      y: data.assets,
                      type: 'heatmap',
                      colorscale: [
                        [0, 'var(--color-negative)'],
                        [0.5, 'var(--bg-surface)'],
                        [1, 'var(--color-positive)']
                      ],
                      text: data.matrix.map(row =>
                        row.map(v => (typeof v === 'number' ? v.toFixed(2) : ''))
                      ),
                      texttemplate: '%{text}',
                      textfont: {
                        family: 'Inter, sans-serif',
                        size: 13,
                        color: '#ffffff',
                      },
                      hoverongaps: false,
                      hovertemplate: '%{y} ↔ %{x}: %{z:.2f}<extra></extra>',
                      zmin: -1,
                      zmax: 1
                    }
                  ]}
                  layout={{
                    autosize: true,
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    margin: { t: 20, r: 20, l: 60, b: 60 },
                    xaxis: {
                      color: 'var(--text-muted)',
                      gridcolor: 'var(--border-color)',
                      tickangle: -45
                    },
                    yaxis: {
                      color: 'var(--text-muted)',
                      gridcolor: 'var(--border-color)'
                    },
                    font: { color: 'var(--text-main)', family: 'Inter' },
                    annotations: heatmapAnnotations,
                  }}
                  useResizeHandler={true}
                  style={{ width: '100%', height: '100%' }}
                  config={{ displayModeBar: false, responsive: true }}
                />
              </div>
            </Card>

            {/* Right Column: Diversification Analysis & Market Dynamics */}
            <div className="flex flex-col space-y-6">
              <Card>
                <CardHeader className="py-3">
                  <CardTitle className="text-sm flex items-center">
                    <Info size={16} className="text-secondary mr-2" />
                    Diversification Analysis
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-sm text-text-muted space-y-4 leading-relaxed">
                    <p className="text-xs">
                      Correlation measures the statistical relationship between asset returns.
                    </p>
                    <div className="space-y-2.5">
                      <div className="flex items-start">
                        <div className="w-3 h-3 mt-1 mr-2 rounded bg-positive flex-shrink-0"></div>
                        <div>
                          <strong className="text-text-main text-xs block">+1.0</strong>
                          <span className="text-[11px]">Strong positive relationship</span>
                        </div>
                      </div>
                      <div className="flex items-start">
                        <div className="w-3 h-3 mt-1 mr-2 rounded bg-surface border border-border flex-shrink-0"></div>
                        <div>
                          <strong className="text-text-main text-xs block">0.0</strong>
                          <span className="text-[11px]">Little/no linear relationship</span>
                        </div>
                      </div>
                      <div className="flex items-start">
                        <div className="w-3 h-3 mt-1 mr-2 rounded bg-negative flex-shrink-0"></div>
                        <div>
                          <strong className="text-text-main text-xs block">-1.0</strong>
                          <span className="text-[11px]">Strong negative relationship</span>
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 p-3 bg-surface-highlight/40 rounded-md border border-border/60 text-xs text-text-main/90 leading-normal">
                      Lower correlation between assets can improve diversification by reducing how strongly portfolio returns move together. Portfolio optimization evaluates the resulting risk and return.
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="py-3">
                  <CardTitle className="text-sm flex items-center">
                    <Activity size={16} className="text-primary mr-2" />
                    Market Dynamics
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-xs text-text-muted leading-relaxed">
                    <p>
                      Asset relationships can change over time. Rolling correlation can be used to examine how these relationships change across different market conditions.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* ── ROLLING CORRELATION SECTION ─────────────────────────────────── */}
          {rollingTraces.length > 0 && (
            <Card>
              <CardHeader className="py-3 flex flex-row items-center justify-between border-b border-border/50">
                <CardTitle className="text-sm flex items-center">
                  <Activity size={16} className="text-primary mr-2" />
                  Rolling Correlation
                </CardTitle>
                <Badge variant="outline" className="text-[11px] font-mono">
                  90-Day Rolling Correlation
                </Badge>
              </CardHeader>
              <CardContent className="pt-4">
                {/* Latest values summary chips */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {data.rolling_series?.map((s, idx) => (
                    <div
                      key={s.pair}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface-highlight/50 border border-border text-xs font-mono"
                    >
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: SERIES_COLORS[idx % SERIES_COLORS.length] }}
                      />
                      <span className="font-semibold text-text-main">{s.pair}:</span>
                      <span className="text-text-muted">
                        {s.latest_correlation != null ? s.latest_correlation.toFixed(2) : '—'}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="w-full h-[360px]">
                  <Plot
                    data={rollingTraces}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 20, r: 20, l: 45, b: 50 },
                      xaxis: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        tickangle: -25,
                      },
                      yaxis: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        range: [-1.05, 1.05],
                        zeroline: true,
                        zerolinecolor: 'var(--border-color)',
                      },
                      legend: {
                        orientation: 'h',
                        y: 1.15,
                        x: 0,
                        font: { color: 'var(--text-main)', size: 11 },
                      },
                      font: { color: 'var(--text-main)', family: 'Inter' },
                    }}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* ── RISK SUMMARY (LAYER 2 ASSET STATISTICS) ────────────────────── */}
          {data.risk_inputs && data.risk_inputs.length > 0 && (
            <Card>
              <CardHeader className="py-3 flex flex-row items-center justify-between border-b border-border/50">
                <CardTitle className="text-sm flex items-center">
                  <Activity size={16} className="text-secondary mr-2" />
                  Risk Summary
                </CardTitle>
                <span className="text-[11px] text-text-muted font-mono">
                  Layer 2 · asset_statistics
                </span>
              </CardHeader>
              <CardContent className="pt-4 p-0 sm:p-4">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border text-text-muted text-[11px] uppercase tracking-wider">
                        <th className="pb-2.5 font-semibold">Asset</th>
                        <th className="pb-2.5 font-semibold text-right">Annualized Volatility</th>
                        <th className="pb-2.5 font-semibold text-right">Sharpe Ratio</th>
                        <th className="pb-2.5 font-semibold text-right">Maximum Drawdown</th>
                        <th className="pb-2.5 font-semibold text-right">Annualized Return</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40 font-mono">
                      {data.risk_inputs.map(item => (
                        <tr key={item.symbol} className="hover:bg-surface-highlight/30 transition-colors">
                          <td className="py-3">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-text-main text-sm">{item.symbol}</span>
                              <span className="text-text-muted font-sans text-xs hidden sm:inline">
                                {item.name}
                              </span>
                              {item.asset_type && (
                                <Badge variant="outline" className="text-[10px] uppercase font-sans">
                                  {item.asset_type}
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="py-3 text-right text-text-main font-semibold">
                            {pct(item.annualized_volatility)}
                          </td>
                          <td className="py-3 text-right text-text-main font-semibold">
                            {fmt(item.sharpe_ratio)}
                          </td>
                          <td className="py-3 text-right text-negative font-semibold">
                            {pct(item.max_drawdown)}
                          </td>
                          <td className="py-3 text-right text-positive font-semibold">
                            {pct(item.annualized_return)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* ── PORTFOLIO OPTIMIZATION CONNECTION ──────────────────────────── */}
          <Card className="border-primary/20 bg-surface/80">
            <CardContent className="p-4 sm:p-6">
              <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm font-semibold text-text-main">
                    <Layers size={16} className="text-primary" />
                    Portfolio Optimization Connection
                  </div>
                  <p className="text-xs text-text-muted">
                    These correlation and risk metrics are inputs used by portfolio optimization.
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  {data.covariance_matrix && data.covariance_matrix.length > 0 && (
                    <button
                      onClick={() => setShowCovariance(!showCovariance)}
                      className="px-3 py-1.5 rounded-lg border border-border text-xs text-text-muted hover:text-text-main hover:bg-surface-highlight transition-colors cursor-pointer"
                    >
                      {showCovariance ? 'Hide Covariance Inputs' : 'Portfolio Risk Inputs'}
                    </button>
                  )}
                  <button
                    onClick={() => navigate('/portfolio')}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary/90 transition-colors shadow-sm cursor-pointer"
                  >
                    Open Portfolio Optimization
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>

              {/* Optional Expandable Covariance Matrix */}
              {showCovariance && data.covariance_matrix && (
                <div className="mt-4 pt-4 border-t border-border animate-fade-in space-y-2">
                  <p className="text-xs text-text-muted">
                    Covariance Matrix (<span className="font-mono">portfolio_covariance_inputs</span>):
                  </p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono text-left">
                      <thead>
                        <tr className="border-b border-border text-text-muted">
                          <th className="p-2"></th>
                          {data.assets.map(sym => (
                            <th key={sym} className="p-2 font-bold text-text-main">{sym}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40">
                        {data.assets.map((rowSym, rIdx) => (
                          <tr key={rowSym} className="hover:bg-surface-highlight/20">
                            <td className="p-2 font-bold text-text-main">{rowSym}</td>
                            {data.assets.map((colSym, cIdx) => (
                              <td key={colSym} className="p-2 text-text-muted">
                                {data.covariance_matrix?.[rIdx]?.[cIdx]?.toFixed(6) ?? '—'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      );
    })()}
    </div>
  );
}

