import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { RobustnessResponse, AssetsResponse } from '../api/types';
import { Shield } from 'lucide-react';
import { QueryStateWrapper } from '../components/QueryStateWrapper';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';

export function Robustness() {
  const { data: assets } = useQuery<AssetsResponse>({
    queryKey: ['assets'],
    queryFn: async () => (await apiClient.get('/assets')).data
  });

  const [asset, setAsset] = useState<string>('BTC-USD');
  const [strategy, setStrategy] = useState<string>('sma_crossover');

  const { data: robustness, isLoading, error, refetch } = useQuery<RobustnessResponse>({
    queryKey: ['robustness', asset, strategy],
    queryFn: async () => (await apiClient.get(`/robustness?asset=${asset}&strategy=${strategy}`)).data,
    enabled: !!asset && !!strategy
  });

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Parameter Robustness</h1>
        <p className="text-sm text-text-muted mt-1">Grid search across the parameter space to detect curve-fitting.</p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 flex-1">
        <div className="w-full lg:w-[320px] flex-shrink-0">
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm flex items-center">
                <Shield size={16} className="text-primary mr-2" />
                Target Selection
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">Asset</label>
                <select className="input-field py-1.5" value={asset} onChange={e => setAsset(e.target.value)}>
                  {assets && Object.entries(assets).map(([k, v]) => (
                    <option key={k} value={k}>{v.name} ({k})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">Strategy</label>
                <select className="input-field py-1.5" value={strategy} onChange={e => setStrategy(e.target.value)}>
                  <option value="sma_crossover">SMA Crossover</option>
                  <option value="ema_trend">EMA Trend</option>
                  <option value="momentum">Momentum</option>
                  <option value="mean_reversion">Mean Reversion</option>
                </select>
              </div>
              
              <div className="pt-4 border-t border-border/50">
                <div className="bg-surface-hover/30 p-3 rounded-md text-[11px] text-text-muted space-y-2 border border-border/50">
                  <p>A robust strategy should exhibit smooth performance transitions across parameter neighborhoods rather than isolated peaks.</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="flex-1">
          <QueryStateWrapper
            isLoading={isLoading}
            error={error}
            data={robustness}
            onRetry={() => refetch()}
          >
            {(data) => (
              <Card className="h-full flex flex-col">
                <CardHeader className="py-3">
                  <CardTitle className="text-sm">Grid Search Results</CardTitle>
                </CardHeader>
                <div className="flex-1 overflow-x-auto">
                  <table className="w-full text-sm text-left whitespace-nowrap">
                    <thead className="text-[10px] uppercase bg-surface-hover/50 text-text-muted border-b border-border">
                      <tr>
                        <th className="px-4 py-2.5 font-medium">Parameters</th>
                        <th className="px-4 py-2.5 font-medium text-right">CAGR</th>
                        <th className="px-4 py-2.5 font-medium text-right">Sharpe</th>
                        <th className="px-4 py-2.5 font-medium text-right">Max Drawdown</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50">
                      {data.results.map((res, i) => {
                        const { cagr, sharpe, max_drawdown, ...params } = res;
                        
                        return (
                          <tr key={i} className="hover:bg-surface-highlight/30 transition-colors">
                            <td className="px-4 py-2.5 font-mono text-xs text-text-muted">
                              {Object.entries(params).map(([k, v]) => `${k}=${v}`).join(', ')}
                            </td>
                            <td className={`px-4 py-2.5 font-mono text-xs text-right font-medium ${res.cagr >= 0 ? 'text-positive' : 'text-negative'}`}>
                              {(res.cagr * 100).toFixed(2)}%
                            </td>
                            <td className={`px-4 py-2.5 font-mono text-xs text-right font-medium ${res.sharpe >= 1 ? 'text-positive' : (res.sharpe < 0 ? 'text-negative' : 'text-text-main')}`}>
                              {res.sharpe.toFixed(2)}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-xs text-right font-medium text-negative">
                              {(res.max_drawdown * 100).toFixed(2)}%
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </QueryStateWrapper>
        </div>
      </div>
    </div>
  );
}
