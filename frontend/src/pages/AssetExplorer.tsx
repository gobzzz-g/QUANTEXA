import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { AssetExplorerResponse } from '../api/types';
import Plot from 'react-plotly.js';
import {
  Database, Calendar, Info, ChevronDown, FileX,
  AlertCircle, RefreshCw, Loader2,
  Clock
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { Badge } from '../components/Badge';
import { useBatch } from '../contexts/BatchContext';

interface BatchInfo {
  batch_id: string;
  batch_name: string;
}

interface BatchAsset {
  asset_id: string;
  symbol: string;
  name: string;
  asset_type?: string;
}

export function AssetExplorer() {
  const location = useLocation();
  const navigate = useNavigate();
  const { selectedBatchId, setSelectedBatchId } = useBatch();

  const [activeTab, setActiveTab] = useState<'price' | 'returns' | 'drawdown'>('price');
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);

  // 1. Fetch batches list for batch dropdown
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

  // 2. Fetch assets belonging strictly to the selected batch
  const {
    data: batchAssetsResp,
    isLoading: assetsLoading,
    isError: assetsError,
  } = useQuery<{ batch_id: string; assets: BatchAsset[] }>({
    queryKey: ['batch-assets', effectiveBatchId],
    queryFn: async () => (await apiClient.get(`/financial-agent/batch/${effectiveBatchId}/assets`)).data,
    enabled: !!effectiveBatchId,
    staleTime: 30_000,
  });
  const batchAssets = batchAssetsResp?.assets ?? [];

  // Set default selected asset from navigation state or first available asset
  useEffect(() => {
    if (batchAssets.length > 0) {
      const navAsset = (location.state as { asset?: string })?.asset;
      if (navAsset && batchAssets.some(a => a.symbol === navAsset)) {
        setSelectedAsset(navAsset);
      } else if (!selectedAsset || !batchAssets.some(a => a.symbol === selectedAsset)) {
        setSelectedAsset(batchAssets[0].symbol);
      }
    } else {
      setSelectedAsset(null);
    }
  }, [batchAssets, location.state]);

  // 3. Fetch deep-dive explorer data for the selected asset in the selected batch
  const {
    data: explorerData,
    isLoading: explorerLoading,
    isError: explorerError,
    error,
    refetch,
  } = useQuery<AssetExplorerResponse>({
    queryKey: ['asset-explorer', effectiveBatchId, selectedAsset],
    queryFn: async () =>
      (await apiClient.get(`/financial-agent/batch/${effectiveBatchId}/asset/${selectedAsset}/explorer`)).data,
    enabled: !!effectiveBatchId && !!selectedAsset,
    staleTime: 30_000,
  });

  const isLoading = batchesLoading || assetsLoading || (!!selectedAsset && explorerLoading);
  const isError = assetsError || explorerError;

  const formatPct = (v: number | null | undefined) => {
    if (v == null) return '—';
    return `${(v * 100).toFixed(2)}%`;
  };

  const formatSignedPct = (v: number | null | undefined) => {
    if (v == null) return '—';
    const prefix = v > 0 ? '+' : '';
    return `${prefix}${(v * 100).toFixed(2)}%`;
  };

  // ─── EMPTY STATE: No Batches ────────────────────────────────────────────────
  if (!batchesLoading && batches.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 animate-fade-in">
        <FileX size={56} className="text-text-muted opacity-40" />
        <div className="text-center">
          <h2 className="text-xl font-bold text-text-main mb-2">No analysis batches available</h2>
          <p className="text-text-muted text-sm mb-6">
            Upload a dataset in the Data &amp; Pipeline page to start exploring assets.
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

  // ─── EMPTY STATE: Batch has no assets ───────────────────────────────────────
  if (!assetsLoading && batchAssets.length === 0 && effectiveBatchId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 animate-fade-in">
        <FileX size={56} className="text-text-muted opacity-40" />
        <div className="text-center">
          <h2 className="text-xl font-bold text-text-main mb-2">No assets available in this batch</h2>
          <p className="text-text-muted text-sm mb-6">
            The selected batch ({effectiveBatchId}) contains no ingested asset records.
          </p>
        </div>
      </div>
    );
  }

  const profile = explorerData?.profile;
  const pv = explorerData?.price_volume;
  const rr = explorerData?.rolling_returns;
  const dd = explorerData?.drawdown;

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in max-w-7xl mx-auto w-full pb-8 p-4 md:p-6">
      {/* ── HEADER ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-text-main">Asset Explorer</h1>
          <p className="text-sm text-text-muted mt-1">
            Single-asset deep-dive analysis, price action, rolling returns, and drawdown.
          </p>
        </div>

        {/* Controls: Batch Selector + Asset Selector */}
        <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3 w-full md:w-auto">
          {/* Batch Selector */}
          <div className="flex flex-col gap-1 min-w-[200px] w-full sm:w-auto">
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

          {/* Asset Selector Pills */}
          {batchAssets.length > 0 && (
            <div className="flex flex-col gap-1 w-full sm:w-auto">
              <label className="text-[10px] uppercase font-bold text-text-muted tracking-wider">
                Batch Asset
              </label>
              <div className="flex flex-wrap gap-1.5 bg-surface-highlight/30 p-1 rounded-lg border border-border">
                {batchAssets.map(a => (
                  <button
                    key={a.symbol}
                    onClick={() => setSelectedAsset(a.symbol)}
                    className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all duration-200 ${
                      selectedAsset === a.symbol
                        ? 'bg-primary text-white shadow-sm'
                        : 'bg-surface text-text-muted hover:text-text-main hover:bg-surface-hover border border-transparent'
                    }`}
                  >
                    {a.name || a.symbol} ({a.symbol})
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── LOADING STATE ────────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="flex items-center justify-center gap-3 py-28 text-text-muted">
          <Loader2 size={28} className="animate-spin text-primary" />
          <span className="text-sm font-medium">Loading asset data for {selectedAsset}…</span>
        </div>
      )}

      {/* ── ERROR STATE ──────────────────────────────────────────────────────── */}
      {isError && !isLoading && (
        <div className="flex flex-col items-center justify-center space-y-4 text-center py-24">
          <AlertCircle size={48} className="text-negative" />
          <h2 className="text-xl font-bold text-text-main">
            Unable to load data for this asset in the selected batch.
          </h2>
          <p className="text-text-muted max-w-md text-sm">
            {error instanceof Error ? error.message : 'Historical data could not be retrieved.'}
          </p>
          <button
            onClick={() => refetch()}
            className="btn-secondary flex items-center gap-2 px-5 py-2 rounded-full text-sm mt-2"
          >
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      )}

      {/* ── MAIN CONTENT ─────────────────────────────────────────────────────── */}
      {!isLoading && !isError && explorerData && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1">
          {/* MAIN CHART AREA (3 cols) */}
          <div className="lg:col-span-3 flex flex-col space-y-4">
            <Card className="flex-1 flex flex-col min-h-[600px] shadow-sm">
              <CardHeader className="py-3 border-b border-border/50 flex flex-row items-center justify-between">
                <div className="flex space-x-6">
                  <button
                    onClick={() => setActiveTab('price')}
                    className={`text-sm font-semibold pb-1.5 border-b-2 transition-colors ${
                      activeTab === 'price'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-text-muted hover:text-text-main'
                    }`}
                  >
                    Price &amp; Volume
                  </button>
                  <button
                    onClick={() => setActiveTab('returns')}
                    className={`text-sm font-semibold pb-1.5 border-b-2 transition-colors ${
                      activeTab === 'returns'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-text-muted hover:text-text-main'
                    }`}
                  >
                    Rolling Returns
                  </button>
                  <button
                    onClick={() => setActiveTab('drawdown')}
                    className={`text-sm font-semibold pb-1.5 border-b-2 transition-colors ${
                      activeTab === 'drawdown'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-text-muted hover:text-text-main'
                    }`}
                  >
                    Drawdown
                  </button>
                </div>

                <div className="text-xs font-mono text-text-muted">
                  {explorerData.name} ({explorerData.symbol})
                </div>
              </CardHeader>

              <div className="flex-1 w-full p-2 min-h-[500px]">
                {/* TAB 1: PRICE & VOLUME */}
                {activeTab === 'price' && pv && (
                  <Plot
                    data={[
                      {
                        x: pv.dates,
                        open: pv.open,
                        high: pv.high,
                        low: pv.low,
                        close: pv.close,
                        type: 'candlestick',
                        xaxis: 'x',
                        yaxis: 'y',
                        name: 'Price',
                        increasing: { line: { color: '#10B981' } },
                        decreasing: { line: { color: '#EF4444' } },
                      },
                      {
                        x: pv.dates,
                        y: pv.volume,
                        type: 'bar',
                        xaxis: 'x',
                        yaxis: 'y2',
                        name: 'Trading Volume',
                        marker: { color: 'rgba(59, 130, 246, 0.25)' },
                      },
                    ]}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 20, r: 40, l: 60, b: 40 },
                      xaxis: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        rangeslider: { visible: false },
                        type: 'date',
                        showgrid: true,
                        tickfont: { family: 'Inter', size: 10 },
                      },
                      yaxis: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        domain: [0.28, 1],
                        showgrid: true,
                        tickfont: { family: 'Inter', size: 10 },
                        title: { text: 'Price ($)', font: { size: 10 } },
                      },
                      yaxis2: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        domain: [0, 0.2],
                        showgrid: false,
                        tickfont: { family: 'Inter', size: 9 },
                        title: { text: 'Trading Volume', font: { size: 9 } },
                      },
                      font: { color: 'var(--text-main)', family: 'Inter' },
                      showlegend: false,
                      hovermode: 'x unified',
                    }}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                )}

                {/* TAB 2: ROLLING RETURNS */}
                {activeTab === 'returns' && rr && (
                  <Plot
                    data={[
                      {
                        x: rr.dates,
                        y: rr.returns,
                        type: 'scatter',
                        mode: 'lines',
                        name: rr.label,
                        line: { width: 1.8, color: '#3B82F6' },
                      },
                    ]}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 20, r: 40, l: 60, b: 40 },
                      xaxis: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        type: 'date',
                        showgrid: true,
                        tickfont: { family: 'Inter', size: 10 },
                      },
                      yaxis: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        showgrid: true,
                        zeroline: true,
                        zerolinecolor: 'var(--border-color)',
                        zerolinewidth: 2,
                        tickfont: { family: 'Inter', size: 10 },
                        ticksuffix: '%',
                        title: { text: rr.label, font: { size: 10 } },
                      },
                      font: { color: 'var(--text-main)', family: 'Inter' },
                      showlegend: false,
                      hovermode: 'x unified',
                    }}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                )}

                {/* TAB 3: DRAWDOWN */}
                {activeTab === 'drawdown' && dd && (
                  <Plot
                    data={[
                      {
                        x: dd.dates,
                        y: dd.drawdown,
                        type: 'scatter',
                        mode: 'lines',
                        fill: 'tozeroy',
                        fillcolor: 'rgba(239, 68, 68, 0.15)',
                        name: 'Drawdown',
                        line: { width: 1.8, color: '#EF4444' },
                      },
                    ]}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 20, r: 40, l: 60, b: 40 },
                      xaxis: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        type: 'date',
                        showgrid: true,
                        tickfont: { family: 'Inter', size: 10 },
                      },
                      yaxis: {
                        color: 'var(--text-muted)',
                        gridcolor: 'var(--border-color)',
                        showgrid: true,
                        zeroline: true,
                        zerolinecolor: 'var(--border-color)',
                        tickfont: { family: 'Inter', size: 10 },
                        ticksuffix: '%',
                        title: { text: 'Drawdown (%)', font: { size: 10 } },
                      },
                      font: { color: 'var(--text-main)', family: 'Inter' },
                      showlegend: false,
                      hovermode: 'x unified',
                    }}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                )}
              </div>
            </Card>
          </div>

          {/* RIGHT CONTEXT PANEL: ASSET PROFILE (1 col) */}
          <div className="flex flex-col space-y-6">
            <Card className="shadow-sm">
              <CardHeader className="py-3.5 border-b border-border/50">
                <CardTitle className="flex items-center text-sm font-bold">
                  <Info size={16} className="text-primary mr-2" />
                  Asset Profile
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5">
                {profile && (
                  <div className="space-y-4 text-sm">
                    <div>
                      <div className="text-[10px] text-text-muted uppercase font-bold tracking-wider mb-1">
                        Asset Name
                      </div>
                      <div className="font-bold text-text-main text-base">{profile.name}</div>
                    </div>

                    <div>
                      <div className="text-[10px] text-text-muted uppercase font-bold tracking-wider mb-1">
                        Ticker &amp; Class
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="font-mono font-bold">
                          {profile.symbol}
                        </Badge>
                        <span className="text-[11px] font-semibold text-text-muted px-2 py-0.5 rounded bg-surface-hover border border-border/50">
                          {profile.asset_class}
                        </span>
                      </div>
                    </div>

                    <div>
                      <div className="text-[10px] text-text-muted uppercase font-bold tracking-wider mb-1">
                        Data Source
                      </div>
                      <div className="flex items-center text-text-main font-medium">
                        <Database size={14} className="mr-2 text-primary" />
                        {profile.data_source}
                      </div>
                    </div>

                    <div>
                      <div className="text-[10px] text-text-muted uppercase font-bold tracking-wider mb-1">
                        Last Updated
                      </div>
                      <div className="flex items-center text-text-main font-mono font-semibold">
                        <Calendar size={14} className="mr-2 text-primary" />
                        {profile.last_updated}
                      </div>
                    </div>

                    <div>
                      <div className="text-[10px] text-text-muted uppercase font-bold tracking-wider mb-1">
                        Total Observations
                      </div>
                      <div className="flex items-center text-text-main font-mono font-semibold">
                        <Clock size={14} className="mr-2 text-primary" />
                        {profile.total_observations.toLocaleString()} days
                      </div>
                    </div>

                    {/* Layer 2 Quantitative Metrics */}
                    <div className="pt-4 border-t border-border/50 space-y-3">
                      <div className="text-[10px] text-text-muted uppercase font-bold tracking-wider mb-2">
                        Layer 2 Statistics
                      </div>

                      <div className="flex justify-between items-center text-xs">
                        <span className="text-text-muted font-medium">Annualized Return</span>
                        <span
                          className={`font-mono font-semibold ${
                            profile.annualized_return >= 0 ? 'text-positive' : 'text-negative'
                          }`}
                        >
                          {formatSignedPct(profile.annualized_return)}
                        </span>
                      </div>

                      <div className="flex justify-between items-center text-xs">
                        <span className="text-text-muted font-medium">Annualized Volatility</span>
                        <span className="font-mono font-semibold text-text-main">
                          {formatPct(profile.annualized_volatility)}
                        </span>
                      </div>

                      <div className="flex justify-between items-center text-xs">
                        <span className="text-text-muted font-medium">Sharpe Ratio</span>
                        <span className="font-mono font-semibold text-text-main">
                          {profile.sharpe_ratio.toFixed(2)}
                        </span>
                      </div>

                      <div className="flex justify-between items-center text-xs">
                        <span className="text-text-muted font-medium">Maximum Drawdown</span>
                        <span className="font-mono font-semibold text-negative">
                          {formatPct(profile.max_drawdown)}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
