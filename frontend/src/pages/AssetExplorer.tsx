import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { AssetsResponse, PricesResponse, MetricsResponse } from '../api/types';
import Plot from 'react-plotly.js';
import { Database, Calendar, Info } from 'lucide-react';
import { QueryStateWrapper } from '../components/QueryStateWrapper';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { Badge } from '../components/Badge';

export function AssetExplorer() {
  const { data: assets, isLoading: assetsLoading, error: assetsError } = useQuery<AssetsResponse>({
    queryKey: ['assets'],
    queryFn: async () => (await apiClient.get('/assets')).data
  });

  const [selectedAsset, setSelectedAsset] = useState<string>('BTC-USD');
  const [activeTab, setActiveTab] = useState<'price' | 'returns' | 'drawdown'>('price');

  const { data: prices, isLoading: pricesLoading, error: pricesError } = useQuery<PricesResponse>({
    queryKey: ['prices', selectedAsset],
    queryFn: async () => (await apiClient.get(`/prices?asset=${selectedAsset}`)).data,
    enabled: !!selectedAsset
  });

  const { data: metrics } = useQuery<MetricsResponse>({
    queryKey: ['metrics', selectedAsset],
    queryFn: async () => (await apiClient.get(`/metrics?asset=${selectedAsset}`)).data,
    enabled: !!selectedAsset
  });

  const isLoading = assetsLoading || pricesLoading;
  const error = assetsError || pricesError;

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Asset Explorer</h1>
          <p className="text-sm text-text-muted mt-1">Deep-dive technical analysis and historical data.</p>
        </div>
        
        {assets && (
          <div className="mt-4 md:mt-0 flex gap-2">
            {Object.entries(assets).map(([key, a]) => (
              <button 
                key={key} 
                onClick={() => setSelectedAsset(key)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${selectedAsset === key ? 'bg-primary text-white shadow-sm' : 'bg-surface text-text-muted hover:bg-surface-hover border border-border'}`}
              >
                {a.name} ({key})
              </button>
            ))}
          </div>
        )}
      </div>

      <QueryStateWrapper
        isLoading={isLoading}
        error={error}
        data={(assets && prices) ? { assets, prices } : undefined}
        onRetry={() => {}}
      >
        {({ assets, prices }) => (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1">
            
            {/* MAIN CHART AREA */}
            <div className="lg:col-span-3 flex flex-col space-y-4">
              <Card className="flex-1 flex flex-col min-h-[600px]">
                <CardHeader className="py-3">
                  <div className="flex space-x-6">
                    <button 
                      onClick={() => setActiveTab('price')}
                      className={`text-sm font-medium pb-1 border-b-2 transition-colors ${activeTab === 'price' ? 'border-primary text-primary' : 'border-transparent text-text-muted hover:text-text-main'}`}
                    >
                      Price & Volume
                    </button>
                    <button 
                      onClick={() => setActiveTab('returns')}
                      className={`text-sm font-medium pb-1 border-b-2 transition-colors ${activeTab === 'returns' ? 'border-primary text-primary' : 'border-transparent text-text-muted hover:text-text-main'}`}
                    >
                      Rolling Returns
                    </button>
                    <button 
                      onClick={() => setActiveTab('drawdown')}
                      className={`text-sm font-medium pb-1 border-b-2 transition-colors ${activeTab === 'drawdown' ? 'border-primary text-primary' : 'border-transparent text-text-muted hover:text-text-main'}`}
                    >
                      Drawdown
                    </button>
                  </div>
                </CardHeader>
                <div className="flex-1 w-full p-2">
                  {activeTab === 'price' && (
                    <Plot
                      data={[
                        {
                          x: prices.dates,
                          open: prices.open,
                          high: prices.high,
                          low: prices.low,
                          close: prices.close,
                          type: 'candlestick',
                          xaxis: 'x',
                          yaxis: 'y',
                          name: 'Price',
                          increasing: { line: { color: '#10B981' } },
                          decreasing: { line: { color: '#EF4444' } }
                        },
                        {
                          x: prices.dates,
                          y: prices.volume,
                          type: 'bar',
                          xaxis: 'x',
                          yaxis: 'y2',
                          name: 'Volume',
                          marker: { color: 'rgba(59, 130, 246, 0.2)' }
                        }
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
                          type: 'category',
                          tickmode: 'auto',
                          nticks: 10,
                          showgrid: true
                        },
                        yaxis: { 
                          color: 'var(--text-muted)', 
                          gridcolor: 'var(--border-color)', 
                          domain: [0.3, 1],
                          showgrid: true 
                        },
                        yaxis2: { 
                          color: 'var(--text-muted)', 
                          gridcolor: 'var(--border-color)', 
                          domain: [0, 0.2],
                          showgrid: false 
                        },
                        font: { color: 'var(--text-main)', family: 'Inter' },
                        showlegend: false,
                        hovermode: 'x unified'
                      }}
                      useResizeHandler={true}
                      style={{ width: '100%', height: '100%' }}
                      config={{ displayModeBar: false, responsive: true }}
                    />
                  )}
                  {activeTab === 'returns' && (
                    <div className="w-full h-full flex items-center justify-center text-text-muted">
                      Rolling Returns visualization coming soon.
                    </div>
                  )}
                  {activeTab === 'drawdown' && (
                    <div className="w-full h-full flex items-center justify-center text-text-muted">
                      Drawdown visualization coming soon.
                    </div>
                  )}
                </div>
              </Card>
            </div>

            {/* RIGHT CONTEXT PANEL */}
            <div className="flex flex-col space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center text-sm">
                    <Info size={16} className="text-secondary mr-2" />
                    Asset Profile
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4 text-sm">
                    <div>
                      <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Asset Name</div>
                      <div className="font-semibold text-text-main">{assets[selectedAsset].name}</div>
                    </div>
                    <div>
                      <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Ticker</div>
                      <Badge variant="outline" className="font-mono">{selectedAsset}</Badge>
                    </div>
                    <div>
                      <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Data Source</div>
                      <div className="flex items-center text-text-main">
                        <Database size={14} className="mr-2 text-primary" />
                        {prices.provenance.data_source.toUpperCase()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Last Updated</div>
                      <div className="flex items-center text-text-main">
                        <Calendar size={14} className="mr-2 text-primary" />
                        {prices.provenance.last_bar}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Total Observations</div>
                      <div className="font-mono text-text-main">{prices.dates.length.toLocaleString()} days</div>
                    </div>
                    
                    {metrics && (
                      <div className="pt-4 border-t border-border/50 space-y-3">
                        <div className="flex justify-between items-center">
                          <span className="text-xs text-text-muted">CAGR</span>
                          <span className={`font-mono font-medium ${metrics.cagr >= 0 ? 'text-positive' : 'text-negative'}`}>
                            {(metrics.cagr * 100).toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-xs text-text-muted">Volatility</span>
                          <span className="font-mono font-medium">
                            {(metrics.annualized_volatility * 100).toFixed(2)}%
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
            
          </div>
        )}
      </QueryStateWrapper>
    </div>
  );
}
