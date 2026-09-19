import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { RegimesResponse, AssetsResponse } from '../api/types';
import Plot from 'react-plotly.js';
import { Layers } from 'lucide-react';
import { QueryStateWrapper } from '../components/QueryStateWrapper';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';

export function Regimes() {
  const { data: assets } = useQuery<AssetsResponse>({
    queryKey: ['assets'],
    queryFn: async () => (await apiClient.get('/assets')).data
  });

  const [asset, setAsset] = useState<string>('BTC-USD');

  const { data: regimes, isLoading, error, refetch } = useQuery<RegimesResponse>({
    queryKey: ['regimes', asset],
    queryFn: async () => (await apiClient.get(`/regimes?asset=${asset}`)).data,
    enabled: !!asset
  });

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Market Regimes Analysis</h1>
          <p className="text-sm text-text-muted mt-1">Identify trend states and volatility clusters for adaptive position sizing.</p>
        </div>
        
        {assets && (
          <div className="mt-4 md:mt-0">
            <select className="input-field py-1.5 w-48" value={asset} onChange={e => setAsset(e.target.value)}>
              {Object.entries(assets).map(([k, v]) => (
                <option key={k} value={k}>{v.name} ({k})</option>
              ))}
            </select>
          </div>
        )}
      </div>

      <QueryStateWrapper
        isLoading={isLoading}
        error={error}
        data={regimes}
        onRetry={() => refetch()}
      >
        {(data) => (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 flex-1">
            <Card className="flex flex-col min-h-[400px]">
              <CardHeader className="py-3">
                <CardTitle className="text-sm flex items-center">
                  <Layers size={16} className="text-primary mr-2" />
                  Trend Regime (Bull vs Bear)
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col flex-1 p-4">
                <p className="text-[11px] text-text-muted mb-2">Classified using 200-day Simple Moving Average crossover thresholds.</p>
                <div className="flex-1 w-full relative">
                  <Plot
                    data={[
                      {
                        x: data.dates,
                        y: data.bull_bear,
                        type: 'scatter',
                        mode: 'lines',
                        fill: 'tozeroy',
                        fillcolor: 'rgba(59, 130, 246, 0.1)',
                        line: { color: 'var(--color-primary)', width: 1.5, shape: 'hv' },
                        name: 'Regime'
                      }
                    ]}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 10, r: 10, l: 40, b: 30 },
                      xaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true },
                      yaxis: { 
                        color: 'var(--text-muted)', 
                        gridcolor: 'var(--border-color)', 
                        tickvals: [-1, 0, 1], 
                        ticktext: ['Bear', 'Neutral', 'Bull'],
                        showgrid: true
                      },
                      font: { color: 'var(--text-main)', family: 'Inter' },
                      hovermode: 'x unified'
                    }}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </CardContent>
            </Card>

            <Card className="flex flex-col min-h-[400px]">
              <CardHeader className="py-3">
                <CardTitle className="text-sm flex items-center">
                  <Layers size={16} className="text-negative mr-2" />
                  Volatility Regime
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col flex-1 p-4">
                <p className="text-[11px] text-text-muted mb-2">High Volatility (1) vs Normal/Low (0) based on rolling 30-day standard deviation anomalies.</p>
                <div className="flex-1 w-full relative">
                  <Plot
                    data={[
                      {
                        x: data.dates,
                        y: data.volatility,
                        type: 'scatter',
                        mode: 'lines',
                        fill: 'tozeroy',
                        fillcolor: 'rgba(239, 68, 68, 0.1)',
                        line: { color: 'var(--color-negative)', width: 1.5, shape: 'hv' },
                        name: 'Volatility'
                      }
                    ]}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 10, r: 10, l: 50, b: 30 },
                      xaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true },
                      yaxis: { 
                        color: 'var(--text-muted)', 
                        gridcolor: 'var(--border-color)', 
                        tickvals: [0, 1], 
                        ticktext: ['Normal', 'High Vol'],
                        showgrid: true
                      },
                      font: { color: 'var(--text-main)', family: 'Inter' },
                      hovermode: 'x unified'
                    }}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </QueryStateWrapper>
    </div>
  );
}
