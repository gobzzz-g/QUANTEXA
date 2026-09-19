import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { CorrelationResponse } from '../api/types';
import Plot from 'react-plotly.js';
import { Grid, Info, Activity } from 'lucide-react';
import { QueryStateWrapper } from '../components/QueryStateWrapper';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';

export function Correlation() {
  const { data: correlation, isLoading, error, refetch } = useQuery<CorrelationResponse>({
    queryKey: ['correlation'],
    queryFn: async () => (await apiClient.get('/correlation')).data
  });

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Correlation & Risk</h1>
        <p className="text-sm text-text-muted mt-1">Cross-asset dependencies and portfolio diversification metrics.</p>
      </div>

      <QueryStateWrapper
        isLoading={isLoading}
        error={error}
        data={correlation}
        onRetry={() => refetch()}
      >
        {(data) => (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1">
            <Card className="lg:col-span-3 flex flex-col min-h-[600px]">
              <CardHeader className="py-3">
                <CardTitle className="text-sm flex items-center">
                  <Grid size={16} className="text-primary mr-2" />
                  Cross-Asset Correlation Matrix
                </CardTitle>
              </CardHeader>
              <div className="flex-1 w-full relative p-2">
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
                      hoverongaps: false,
                      zmin: -1,
                      zmax: 1
                    }
                  ]}
                  layout={{
                    autosize: true,
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    margin: { t: 20, r: 20, l: 60, b: 60 },
                    xaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', tickangle: -45 },
                    yaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)' },
                    font: { color: 'var(--text-main)', family: 'Inter' }
                  }}
                  useResizeHandler={true}
                  style={{ width: '100%', height: '100%' }}
                  config={{ displayModeBar: false, responsive: true }}
                />
              </div>
            </Card>

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
                    <p>
                      The correlation matrix measures the statistical relationship between the returns of different assets across the dataset.
                    </p>
                    <div className="space-y-2">
                      <div className="flex items-start">
                        <div className="w-3 h-3 mt-1 mr-2 rounded bg-positive"></div>
                        <div>
                          <strong className="text-text-main text-xs block">+1.0 (Positive)</strong>
                          <span className="text-[11px]">Perfect positive correlation. Assets move together.</span>
                        </div>
                      </div>
                      <div className="flex items-start">
                        <div className="w-3 h-3 mt-1 mr-2 rounded bg-surface border border-border"></div>
                        <div>
                          <strong className="text-text-main text-xs block">0.0 (Neutral)</strong>
                          <span className="text-[11px]">No correlation. Assets move independently.</span>
                        </div>
                      </div>
                      <div className="flex items-start">
                        <div className="w-3 h-3 mt-1 mr-2 rounded bg-negative"></div>
                        <div>
                          <strong className="text-text-main text-xs block">-1.0 (Negative)</strong>
                          <span className="text-[11px]">Perfect negative correlation. Assets move inversely.</span>
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 p-3 bg-surface-highlight/30 rounded-md border border-border/50 text-xs">
                      Quantitative portfolios typically seek uncorrelated return streams to maximize the Sharpe ratio according to Modern Portfolio Theory.
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
                  <div className="text-xs text-text-muted">
                    <p className="mb-2">Asset correlations are not static and tend to increase during market stress (correlation breaks to 1).</p>
                    <p>Monitor the Rolling Correlation (coming soon) to detect structural shifts in market regimes.</p>
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
