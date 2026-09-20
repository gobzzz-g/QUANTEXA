import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Database, 
  UploadCloud, 
  CheckCircle2, 
  XCircle, 
  Loader2, 
  Play, 
  Clock, 
  Layers, 
  ArrowRight, 
  Check, 
  Copy, 
  AlertTriangle, 
  FileSpreadsheet,
  BrainCircuit,
  RefreshCw
} from 'lucide-react';
import { apiClient } from '../api/client';

interface DatasetPreview {
  filename: string;
  row_count: number;
  column_count: number;
  columns: string[];
  detected_assets: string[];
  date_range: { start?: string; end?: string; min_date?: string; max_date?: string };
  missing_values: Record<string, number>;
  duplicate_rows: number;
  invalid_rows: number;
  asset_types: Record<string, string>;
  sample_rows: Record<string, any>[];
}

interface BatchInfo {
  batch_id: string;
  batch_name: string;
  dataset_filename: string;
  status: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

interface LayerRun {
  batch_id: string;
  layer_number: number;
  layer_name: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  rows_processed?: number;
  error_message?: string;
  metadata?: any;
}

const LAYER_CONFIG = [
  { num: 1, name: 'Data Ingestion & Integrity', desc: 'Price verification, deduplication, schema validation' },
  { num: 2, name: 'Quantitative Risk Analytics', desc: 'CAGR, annualized volatility, Sharpe ratio, max drawdown' },
  { num: 3, name: 'Strategy Signal Engine', desc: 'SMA crossover, momentum, mean-reversion signals' },
  { num: 4, name: 'Deterministic Backtesting', desc: 'Equity curve simulation, trades, win rates, benchmark comparison' },
  { num: 5, name: 'Robustness & Market Regimes', desc: 'Regime segmentation (Bull/Bear/Vol) & parameter stress testing' },
  { num: 6, name: 'Classical Portfolio Optimization', desc: 'Markowitz continuous convex optimization (Min Vol & Max Sharpe)' },
  { num: 7, name: 'QUBO Combinatorial Optimization', desc: 'Binary integer formulation solved via classical simulated annealing' },
];

export function DataPipeline() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form State
  const [batchName, setBatchName] = useState('Multi-Asset Benchmark Run');
  const [fileContent, setFileContent] = useState<string>('');
  const [fileName, setFileName] = useState<string>('');
  const [assetTypeOverrides, setAssetTypeOverrides] = useState<Record<string, string>>({});

  // Analysis State
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [activeBatchId, setActiveBatchId] = useState<string>(() => {
    return localStorage.getItem('quantexa_active_batch_id') || 'TEST_BATCH_01';
  });

  const [isCreatingBatch, setIsCreatingBatch] = useState(false);
  const [isStartingPipeline, setIsStartingPipeline] = useState(false);
  const [pipelinePolling, setPipelinePolling] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [layerRuns, setLayerRuns] = useState<LayerRun[]>([]);
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchesLoading, setBatchesLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Fetch batches on mount
  const fetchBatches = async () => {
    setBatchesLoading(true);
    try {
      const res = await apiClient.get('/financial-agent/batches');
      if (Array.isArray(res.data)) {
        setBatches(res.data);
      } else if (res.data && Array.isArray((res.data as any).batches)) {
        setBatches((res.data as any).batches);
      } else {
        setBatches([]);
      }
    } catch (err: any) {
      console.error('Failed to load batches:', err);
      setBatches([]);
    } finally {
      setBatchesLoading(false);
    }
  };

  // Fetch active batch status
  const fetchBatchStatus = async (batchId: string) => {
    try {
      const res = await apiClient.get<{ batch_info: BatchInfo; layer_runs: LayerRun[] }>(
        `/pipeline/status/${batchId}`
      );
      if (res.data) {
        setLayerRuns(res.data.layer_runs || []);
        const currentBatch = res.data.batch_info;
        if (currentBatch && (currentBatch.status === 'COMPLETED' || currentBatch.status === 'FAILED')) {
          setPipelinePolling(false);
          fetchBatches();
        }
      }
    } catch (err: any) {
      console.error('Failed to fetch batch status:', err);
    }
  };

  useEffect(() => {
    fetchBatches();
    if (activeBatchId) {
      fetchBatchStatus(activeBatchId);
    }
  }, [activeBatchId]);

  // Polling effect for active pipeline
  useEffect(() => {
    if (!pipelinePolling || !activeBatchId) return;
    const interval = setInterval(() => {
      fetchBatchStatus(activeBatchId);
    }, 2000);
    return () => clearInterval(interval);
  }, [pipelinePolling, activeBatchId]);

  // Handle CSV file selection
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      setFileContent(text);
      triggerPreview(file.name, text);
    };
    reader.readAsText(file);
  };

  // Load sample dataset
  const loadSampleDataset = async () => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const sampleCsv = `date,asset,asset_type,open,high,low,close,volume
2020-01-02,BTC,CRYPTOCURRENCY,7202.55,7212.15,6935.27,6985.47,20802083465
2020-01-02,GOLD,COMMODITY,1518.10,1528.70,1518.00,1524.50,214
2020-01-02,NVDA,EQUITY,5.93,5.96,5.88,5.96,237536000
2020-01-03,BTC,CRYPTOCURRENCY,6984.43,7413.72,6914.99,7344.88,28111481032
2020-01-03,GOLD,COMMODITY,1530.10,1552.70,1530.10,1549.20,107
2020-01-03,NVDA,EQUITY,5.84,5.91,5.81,5.86,205384000
2020-01-06,BTC,CRYPTOCURRENCY,7411.32,7781.18,7409.22,7769.22,23276261598
2020-01-06,GOLD,COMMODITY,1580.00,1588.00,1560.00,1568.80,332
2020-01-06,NVDA,EQUITY,5.77,5.93,5.74,5.90,267992000`;
      
      setFileName('sample_btc_gold_nvda.csv');
      setFileContent(sampleCsv);
      await triggerPreview('sample_btc_gold_nvda.csv', sampleCsv);
    } catch (err: any) {
      setPreviewError(err.message || 'Failed to load sample dataset');
    } finally {
      setPreviewLoading(false);
    }
  };

  // Preview Dataset API Call
  const triggerPreview = async (name: string, content: string) => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const res = await apiClient.post<DatasetPreview>('/pipeline/preview-dataset', {
        filename: name,
        content: content
      });
      setPreview(res.data);
      if (res.data?.asset_types) {
        setAssetTypeOverrides(res.data.asset_types);
      }
    } catch (err: any) {
      setPreviewError(err.response?.data?.detail || err.message || 'Failed to validate dataset');
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // Create Batch
  const handleCreateBatch = async () => {
    if (!fileContent || !fileName) {
      alert('Please select or load a CSV dataset first.');
      return;
    }
    setIsCreatingBatch(true);
    setStatusError(null);
    try {
      const res = await apiClient.post<{ batch_id: string; batch_name: string; status: string }>(
        '/pipeline/create-batch',
        {
          batch_name: batchName,
          dataset_filename: fileName,
          content: fileContent,
          asset_type_overrides: assetTypeOverrides
        }
      );
      const newBatchId = res.data.batch_id;
      setActiveBatchId(newBatchId);
      localStorage.setItem('quantexa_active_batch_id', newBatchId);
      await fetchBatches();
      await fetchBatchStatus(newBatchId);
    } catch (err: any) {
      setStatusError(err.response?.data?.detail || err.message || 'Failed to create batch');
    } finally {
      setIsCreatingBatch(false);
    }
  };

  // Start Pipeline
  const handleStartPipeline = async () => {
    if (!activeBatchId) {
      alert('Please create or select an active batch first.');
      return;
    }
    setIsStartingPipeline(true);
    setStatusError(null);
    try {
      await apiClient.post(`/pipeline/run?batch_id=${activeBatchId}&async_mode=true`);
      setPipelinePolling(true);
      fetchBatchStatus(activeBatchId);
    } catch (err: any) {
      setStatusError(err.response?.data?.detail || err.message || 'Failed to start pipeline execution');
    } finally {
      setIsStartingPipeline(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const selectBatch = (bId: string) => {
    setActiveBatchId(bId);
    localStorage.setItem('quantexa_active_batch_id', bId);
    fetchBatchStatus(bId);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-text-main">Financial Data & Pipeline Management</h1>
            <span className="px-2 py-0.5 text-xs font-semibold rounded bg-primary/10 text-primary border border-primary/20">
              Layers 1–7 Ingestion
            </span>
          </div>
          <p className="text-sm text-text-muted mt-1">
            Deterministic CSV validation, UUID batch provisioning, and sequential Layer 1 → Layer 7 financial analysis.
          </p>
        </div>

        {/* Active Batch Indicator Badge */}
        <div className="flex items-center gap-3 bg-surface border border-border p-2.5 rounded-lg">
          <div className="p-2 bg-primary/10 rounded-md text-primary">
            <Database className="w-5 h-5" />
          </div>
          <div className="text-xs">
            <div className="text-text-muted font-medium">Active Batch ID</div>
            <div className="font-mono font-bold text-text-main flex items-center gap-1.5">
              <span>{activeBatchId}</span>
              <button 
                onClick={() => copyToClipboard(activeBatchId)} 
                className="hover:text-primary transition-colors"
                title="Copy Batch ID"
              >
                {copiedId === activeBatchId ? <Check className="w-3.5 h-3.5 text-positive" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Upload & Preview (Left) vs. Pipeline Execution (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Dataset Upload & Validation (5 cols) */}
        <div className="lg:col-span-6 space-y-6">
          <div className="bg-surface border border-border rounded-xl p-5 shadow-sm space-y-5">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-primary" />
                <h2 className="font-semibold text-text-main">1. Dataset Upload & Configuration</h2>
              </div>
              <button
                onClick={loadSampleDataset}
                className="text-xs text-primary hover:underline font-medium flex items-center gap-1"
              >
                <RefreshCw className="w-3 h-3" /> Load Sample CSV
              </button>
            </div>

            {/* Batch Name Input */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                Batch Name
              </label>
              <input
                type="text"
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
                placeholder="e.g. Q3 Multi-Asset Volatility Run"
                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm text-text-main focus:outline-none focus:border-primary transition-colors"
              />
            </div>

            {/* File Dropzone */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                Dataset File (CSV)
              </label>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                accept=".csv"
                className="hidden"
              />
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-border hover:border-primary/50 bg-background/50 hover:bg-surface-hover/50 rounded-xl p-6 text-center cursor-pointer transition-all duration-200"
              >
                <UploadCloud className="w-8 h-8 text-primary mx-auto mb-2 opacity-80" />
                <p className="text-sm font-medium text-text-main">
                  {fileName ? fileName : 'Click to select or drop CSV dataset'}
                </p>
                <p className="text-xs text-text-muted mt-1">
                  Required: <code className="text-primary">date, asset, close</code> • Preferred: <code className="text-primary">asset_type, open, high, low, volume</code>
                </p>
              </div>
            </div>

            {/* Preview Status / Loading */}
            {previewLoading && (
              <div className="flex items-center justify-center py-4 text-sm text-text-muted gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-primary" /> Validating CSV structure & schema...
              </div>
            )}

            {previewError && (
              <div className="p-3 bg-negative/10 border border-negative/20 rounded-lg text-xs text-negative flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{previewError}</span>
              </div>
            )}

            {/* Dataset Preview Metadata Card */}
            {preview && (
              <div className="bg-background/80 border border-border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between text-xs font-semibold text-text-main border-b border-border pb-2">
                  <span>Dataset Validation Passed</span>
                  <span className="text-positive flex items-center gap-1 font-mono">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Valid Schema
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="p-2 bg-surface rounded border border-border">
                    <div className="text-text-muted">Total Rows</div>
                    <div className="font-mono font-bold text-text-main text-sm">{preview.row_count.toLocaleString()}</div>
                  </div>
                  <div className="p-2 bg-surface rounded border border-border">
                    <div className="text-text-muted">Missing Values</div>
                    <div className={`font-mono font-bold text-sm ${Object.values(preview.missing_values || {}).some(v => v > 0) ? 'text-warning' : 'text-positive'}`}>
                      {Object.values(preview.missing_values || {}).reduce((a, b) => a + b, 0)}
                    </div>
                  </div>
                  <div className="p-2 bg-surface rounded border border-border">
                    <div className="text-text-muted">Duplicates</div>
                    <div className="font-mono font-bold text-positive text-sm">{preview.duplicate_rows}</div>
                  </div>
                </div>

                {/* Detected Assets & Types */}
                <div className="space-y-1.5 pt-1">
                  <div className="text-[11px] font-semibold text-text-muted uppercase">Detected Assets & Classifications</div>
                  <div className="flex flex-wrap gap-1.5">
                    {preview.detected_assets.map((asset) => (
                      <div key={asset} className="flex items-center gap-1.5 px-2 py-1 bg-surface border border-border rounded text-xs">
                        <span className="font-bold text-primary font-mono">{asset}</span>
                        <select
                          value={assetTypeOverrides[asset] || preview.asset_types?.[asset] || 'EQUITY'}
                          onChange={(e) => setAssetTypeOverrides({ ...assetTypeOverrides, [asset]: e.target.value })}
                          className="bg-background border border-border rounded text-[10px] text-text-muted px-1 py-0.5 focus:outline-none"
                        >
                          <option value="CRYPTOCURRENCY">CRYPTOCURRENCY</option>
                          <option value="COMMODITY">COMMODITY</option>
                          <option value="EQUITY">EQUITY</option>
                          <option value="ETF">ETF</option>
                          <option value="FOREX">FOREX</option>
                        </select>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Date range */}
                <div className="text-xs text-text-muted pt-1 flex items-center justify-between">
                  <span>Sample Date Range:</span>
                  <span className="font-mono text-text-main font-medium">
                    {preview.date_range?.min_date || preview.date_range?.start} → {preview.date_range?.max_date || preview.date_range?.end}
                  </span>
                </div>
              </div>
            )}

            {/* Create Batch Button */}
            <button
              onClick={handleCreateBatch}
              disabled={isCreatingBatch || !preview}
              className={`w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2 ${
                preview && !isCreatingBatch
                  ? 'bg-primary text-white hover:bg-primary/90 shadow-sm shadow-primary/25 cursor-pointer'
                  : 'bg-surface border border-border text-text-muted cursor-not-allowed opacity-60'
              }`}
            >
              {isCreatingBatch ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Provisioning UUID Batch...
                </>
              ) : (
                <>
                  <Database className="w-4 h-4" /> 2. Create Analysis Batch
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right Column: Pipeline Execution & Status (6 cols) */}
        <div className="lg:col-span-6 space-y-6">
          <div className="bg-surface border border-border rounded-xl p-5 shadow-sm space-y-5">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Layers className="w-5 h-5 text-primary" />
                <h2 className="font-semibold text-text-main">3. Sequential Pipeline Execution (Layers 1–7)</h2>
              </div>
              <button
                onClick={handleStartPipeline}
                disabled={isStartingPipeline || pipelinePolling || !activeBatchId}
                className={`py-1.5 px-3 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
                  activeBatchId && !pipelinePolling
                    ? 'bg-primary text-white hover:bg-primary/90 shadow-sm cursor-pointer'
                    : 'bg-surface border border-border text-text-muted cursor-not-allowed opacity-60'
                }`}
              >
                {isStartingPipeline || pipelinePolling ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Running Pipeline...
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5" /> Start Analysis
                  </>
                )}
              </button>
            </div>

            {statusError && (
              <div className="p-3 bg-negative/10 border border-negative/20 rounded-lg text-xs text-negative flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{statusError}</span>
              </div>
            )}

            {/* Pipeline Layers Tracker */}
            <div className="space-y-2">
              {LAYER_CONFIG.map((layer) => {
                const run = layerRuns.find((r) => r.layer_number === layer.num);
                const status = run?.status || 'PENDING';
                const isCompleted = status === 'COMPLETED';
                const isFailed = status === 'FAILED';
                const isRunning = status === 'RUNNING';

                return (
                  <div
                    key={layer.num}
                    className={`p-3 rounded-lg border transition-all duration-200 flex items-center justify-between ${
                      isCompleted 
                        ? 'bg-positive/5 border-positive/20' 
                        : isFailed 
                        ? 'bg-negative/5 border-negative/20'
                        : isRunning 
                        ? 'bg-primary/5 border-primary/30 animate-pulse'
                        : 'bg-background/40 border-border/80'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                        isCompleted 
                          ? 'bg-positive/20 text-positive' 
                          : isFailed 
                          ? 'bg-negative/20 text-negative'
                          : isRunning 
                          ? 'bg-primary/20 text-primary'
                          : 'bg-surface border border-border text-text-muted'
                      }`}>
                        {layer.num}
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-text-main flex items-center gap-2">
                          <span>{layer.name}</span>
                          {run?.rows_processed !== undefined && run.rows_processed > 0 && (
                            <span className="text-[10px] font-mono text-text-muted">({run.rows_processed} rows)</span>
                          )}
                        </div>
                        <div className="text-[11px] text-text-muted">{layer.desc}</div>
                        {run?.error_message && (
                          <div className="text-[10px] text-negative font-mono mt-0.5">{run.error_message}</div>
                        )}
                      </div>
                    </div>

                    <div className="shrink-0 flex items-center gap-2">
                      {isCompleted && (
                        <span className="flex items-center gap-1 text-xs font-semibold text-positive">
                          <CheckCircle2 className="w-4 h-4" /> Done
                        </span>
                      )}
                      {isFailed && (
                        <span className="flex items-center gap-1 text-xs font-semibold text-negative">
                          <XCircle className="w-4 h-4" /> Failed
                        </span>
                      )}
                      {isRunning && (
                        <span className="flex items-center gap-1 text-xs font-semibold text-primary">
                          <Loader2 className="w-4 h-4 animate-spin" /> Running
                        </span>
                      )}
                      {status === 'PENDING' && (
                        <span className="text-xs text-text-muted font-medium">Pending</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Next Step / OpenClaw Call to Action */}
            <div className="bg-primary/5 border border-primary/20 rounded-lg p-4 flex items-center justify-between">
              <div>
                <div className="text-xs font-bold text-text-main flex items-center gap-1.5">
                  <BrainCircuit className="w-4 h-4 text-primary" /> Ask OpenClaw About This Batch
                </div>
                <div className="text-xs text-text-muted mt-0.5">
                  Query capital allocation (e.g. ₹1 Lakh low risk), Markowitz weights, and QUBO quantum-inspired results.
                </div>
              </div>
              <button
                onClick={() => navigate('/ai-research')}
                className="px-3 py-1.5 bg-primary text-white text-xs font-semibold rounded-md hover:bg-primary/90 flex items-center gap-1 shrink-0"
              >
                <span>Launch OpenClaw</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Section 4: Batch History Table */}
      <div className="bg-surface border border-border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-primary" />
            <h2 className="font-semibold text-text-main">Batch Execution History & Scoping</h2>
          </div>
          <button
            onClick={fetchBatches}
            disabled={batchesLoading}
            className="text-xs text-text-muted hover:text-text-main flex items-center gap-1"
          >
            <RefreshCw className={`w-3 h-3 ${batchesLoading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-background/80 text-text-muted border-b border-border uppercase font-semibold">
              <tr>
                <th className="py-2.5 px-3">Batch Name</th>
                <th className="py-2.5 px-3">UUID Batch ID</th>
                <th className="py-2.5 px-3">Dataset Source</th>
                <th className="py-2.5 px-3">Pipeline Status</th>
                <th className="py-2.5 px-3">Created Date</th>
                <th className="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {(Array.isArray(batches) ? batches : []).map((batch) => {
                const isCurrent = batch.batch_id === activeBatchId;
                const isDone = batch.status === 'COMPLETED';
                const isFail = batch.status === 'FAILED';

                return (
                  <tr 
                    key={batch.batch_id} 
                    className={`hover:bg-surface-hover/50 transition-colors ${
                      isCurrent ? 'bg-primary/5' : ''
                    }`}
                  >
                    <td className="py-3 px-3 font-semibold text-text-main flex items-center gap-2">
                      {isCurrent && <span className="w-1.5 h-1.5 rounded-full bg-primary" />}
                      {batch.batch_name}
                    </td>
                    <td className="py-3 px-3 font-mono text-text-muted">
                      <div className="flex items-center gap-1">
                        <span>{batch.batch_id}</span>
                        <button 
                          onClick={() => copyToClipboard(batch.batch_id)} 
                          className="hover:text-primary transition-colors"
                        >
                          <Copy className="w-3 h-3" />
                        </button>
                      </div>
                    </td>
                    <td className="py-3 px-3 text-text-muted font-mono">{batch.dataset_filename || 'raw_dataset.csv'}</td>
                    <td className="py-3 px-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        isDone 
                          ? 'bg-positive/15 text-positive border border-positive/30' 
                          : isFail 
                          ? 'bg-negative/15 text-negative border border-negative/30'
                          : 'bg-primary/15 text-primary border border-primary/30'
                      }`}>
                        {batch.status}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-text-muted">
                      {new Date(batch.created_at).toLocaleDateString()} {new Date(batch.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={() => selectBatch(batch.batch_id)}
                        disabled={isCurrent}
                        className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                          isCurrent
                            ? 'bg-primary/20 text-primary cursor-default'
                            : 'bg-surface border border-border hover:border-primary text-text-main hover:text-primary cursor-pointer'
                        }`}
                      >
                        {isCurrent ? 'Active Batch' : 'Select Batch'}
                      </button>
                    </td>
                  </tr>
                );
              })}

              {(!Array.isArray(batches) || batches.length === 0) && !batchesLoading && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-text-muted">
                    No analysis batches recorded yet. Upload a dataset to create the first batch.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
