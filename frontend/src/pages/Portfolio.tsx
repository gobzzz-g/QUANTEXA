import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { AssetsResponse, PortfolioResponse } from '../api/types';
import { PieChart, List, TrendingUp, Shield, Activity, Target } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import Plot from 'react-plotly.js';
import { QueryStateWrapper } from '../components/QueryStateWrapper';

export function Portfolio() {
  const { data: assets } = useQuery<AssetsResponse>({
    queryKey: ['assets'],
    queryFn: async () => (await apiClient.get('/assets')).data
  });

  const availableAssets = assets ? Object.keys(assets) : [];
  const [selectedAssets, setSelectedAssets] = useState<string[]>(['BTC-USD', 'NVDA', 'GC=F']);
  const [method, setMethod] = useState<string>('max_sharpe');
  const [useQuantum, setUseQuantum] = useState<boolean>(false);

  const toggleAsset = (asset: string) => {
    setSelectedAssets(prev => 
      prev.includes(asset) 
        ? prev.filter(a => a !== asset)
        : [...prev, asset]
    );
  };

  const { data: portfolio, isLoading, error, refetch } = useQuery<PortfolioResponse>({
    queryKey: ['portfolio', selectedAssets, method, useQuantum],
    queryFn: async () => (await apiClient.post('/portfolio', {
      assets: selectedAssets,
      method: method,
      use_quantum_baseline: useQuantum
    })).data,
    enabled: selectedAssets.length >= 2,
    retry: false
  });

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Portfolio Optimization</h1>
          <p className="text-sm text-text-muted mt-1">
            Construct optimal portfolios using classical solvers and quantum QUBO baselines.
          </p>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 flex-1">
        <div className="w-full lg:w-[320px] flex-shrink-0 flex flex-col gap-6">
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm flex items-center">
                <List size={16} className="text-primary mr-2" />
                Asset Universe
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-[200px] overflow-y-auto pr-2 custom-scrollbar">
                {availableAssets.map(asset => (
                  <label key={asset} className="flex items-center space-x-2 text-sm cursor-pointer p-1.5 hover:bg-surface-hover rounded-md transition-colors">
                    <input 
                      type="checkbox"
                      checked={selectedAssets.includes(asset)}
                      onChange={() => toggleAsset(asset)}
                      className="rounded border-border bg-surface-highlight text-primary focus:ring-primary/20"
                    />
                    <span className="text-text-main">{assets?.[asset]?.name || asset}</span>
                    <span className="text-[10px] text-text-muted ml-auto font-mono">{asset}</span>
                  </label>
                ))}
              </div>
              {selectedAssets.length < 2 && (
                <p className="text-negative text-xs mt-3">Select at least 2 assets to optimize.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm flex items-center">
                <Target size={16} className="text-accent mr-2" />
                Optimization Objective
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="flex items-center space-x-2 text-sm">
                  <input type="radio" checked={!useQuantum && method === 'equal_weight'} onChange={() => { setMethod('equal_weight'); setUseQuantum(false); }} className="text-primary focus:ring-primary/20" />
                  <span>Equal Weight Baseline</span>
                </label>
                <label className="flex items-center space-x-2 text-sm">
                  <input type="radio" checked={!useQuantum && method === 'min_volatility'} onChange={() => { setMethod('min_volatility'); setUseQuantum(false); }} className="text-primary focus:ring-primary/20" />
                  <span>Minimum Volatility (Markowitz)</span>
                </label>
                <label className="flex items-center space-x-2 text-sm">
                  <input type="radio" checked={!useQuantum && method === 'max_sharpe'} onChange={() => { setMethod('max_sharpe'); setUseQuantum(false); }} className="text-primary focus:ring-primary/20" />
                  <span>Maximum Sharpe Ratio</span>
                </label>
              </div>

              <div className="pt-4 border-t border-border/50">
                <label className="flex items-center space-x-2 text-sm text-accent font-medium">
                  <input type="checkbox" checked={useQuantum} onChange={e => setUseQuantum(e.target.checked)} className="rounded border-border text-accent focus:ring-accent/20" />
                  <span>Use QUBO Quantum Baseline</span>
                </label>
                <p className="text-[10px] text-text-muted mt-2 leading-relaxed">
                  Formulates a discrete binary selection problem (Quadratic Unconstrained Binary Optimization) solved via simulated annealing baseline.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="flex-1 flex flex-col gap-6">
          <QueryStateWrapper
            isLoading={isLoading}
            error={error}
            data={portfolio}
            onRetry={() => refetch()}
          >
            {(data) => {
              const weights = data.optimization.weights;
              const labels = Object.keys(weights);
              const values = Object.values(weights);
              
              // Only keep non-zero weights for pie chart
              const pieLabels = labels.filter((_, i) => values[i] > 0.001);
              const pieValues = values.filter(v => v > 0.001);

              return (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <Card>
                      <CardContent className="p-4 flex flex-col">
                        <span className="text-xs text-text-muted uppercase tracking-wider mb-1 flex items-center">
                          <TrendingUp size={12} className="mr-1 text-positive" /> Expected Return (Ann.)
                        </span>
                        <span className="text-2xl font-mono text-text-main">
                          {(data.optimization.expected_return * 100).toFixed(2)}%
                        </span>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4 flex flex-col">
                        <span className="text-xs text-text-muted uppercase tracking-wider mb-1 flex items-center">
                          <Shield size={12} className="mr-1 text-negative" /> Portfolio Volatility
                        </span>
                        <span className="text-2xl font-mono text-text-main">
                          {(data.optimization.volatility * 100).toFixed(2)}%
                        </span>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4 flex flex-col">
                        <span className="text-xs text-text-muted uppercase tracking-wider mb-1 flex items-center">
                          <Activity size={12} className="mr-1 text-accent" /> Sharpe Ratio
                        </span>
                        <span className="text-2xl font-mono text-text-main">
                          {data.optimization.sharpe_ratio.toFixed(2)}
                        </span>
                      </CardContent>
                    </Card>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1 min-h-[400px]">
                    <Card className="flex flex-col">
                      <CardHeader className="py-3">
                        <CardTitle className="text-sm flex items-center">
                          <PieChart size={16} className="text-primary mr-2" />
                          Optimal Allocation
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="flex-1 p-0 relative">
                        <Plot
                          data={[
                            {
                              values: pieValues,
                              labels: pieLabels,
                              type: 'pie',
                              hole: 0.6,
                              textinfo: 'label+percent',
                              hoverinfo: 'label+percent',
                              marker: {
                                colors: ['#3B82F6', '#10B981', '#8B5CF6', '#F59E0B', '#EF4444', '#EC4899']
                              }
                            }
                          ]}
                          layout={{
                            autosize: true,
                            paper_bgcolor: 'transparent',
                            plot_bgcolor: 'transparent',
                            margin: { t: 20, r: 20, l: 20, b: 20 },
                            font: { color: 'var(--text-main)', family: 'Inter' },
                            showlegend: false
                          }}
                          useResizeHandler={true}
                          style={{ width: '100%', height: '100%', position: 'absolute' }}
                          config={{ displayModeBar: false }}
                        />
                      </CardContent>
                    </Card>

                    <Card className="flex flex-col">
                      <CardHeader className="py-3">
                        <CardTitle className="text-sm">Weight Matrix</CardTitle>
                      </CardHeader>
                      <div className="flex-1 overflow-auto">
                        <table className="w-full text-sm text-left">
                          <thead className="text-[10px] uppercase bg-surface-hover/50 text-text-muted border-b border-border">
                            <tr>
                              <th className="px-4 py-2 font-medium">Asset</th>
                              <th className="px-4 py-2 font-medium text-right">Target Weight</th>
                              <th className="px-4 py-2 font-medium text-right">Expected Ret.</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/50">
                            {labels.map(asset => (
                              <tr key={asset} className="hover:bg-surface-highlight/30">
                                <td className="px-4 py-3 font-medium text-text-main flex items-center gap-2">
                                  <div 
                                    className="w-2 h-2 rounded-full" 
                                    style={{ backgroundColor: (weights[asset] > 0.01) ? '#3B82F6' : 'var(--border-color)' }}
                                  />
                                  {asset}
                                </td>
                                <td className="px-4 py-3 font-mono text-right text-text-main">
                                  {(weights[asset] * 100).toFixed(1)}%
                                </td>
                                <td className="px-4 py-3 font-mono text-right text-text-muted">
                                  {(data.expected_returns[asset] * 100).toFixed(1)}%
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        
                        {data.optimization.qubo_cost !== undefined && (
                          <div className="p-4 mt-4 bg-surface-hover/30 border border-border/50 rounded mx-4">
                            <h4 className="text-xs font-semibold text-accent mb-1">Quantum Simulated Baseline</h4>
                            <div className="flex justify-between text-xs font-mono">
                              <span className="text-text-muted">QUBO Cost Objective:</span>
                              <span className="text-text-main">{data.optimization.qubo_cost.toFixed(4)}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    </Card>
                  </div>
                </>
              );
            }}
          </QueryStateWrapper>
        </div>
      </div>
    </div>
  );
}
