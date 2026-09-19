import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import Plot from 'react-plotly.js';
import { Activity, ShieldCheck, Database, Calendar, TrendingUp, AlertTriangle, ArrowUpRight, ArrowDownRight, Layers, LayoutGrid, Network, Search, Bell } from 'lucide-react';
import { QueryStateWrapper } from '../components/QueryStateWrapper';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { Badge } from '../components/Badge';
import { useNavigate } from 'react-router-dom';

const pct = (val: number) => `${(val * 100).toFixed(2)}%`;

export function Overview() {
  const navigate = useNavigate();
  const [chartPeriod, setChartPeriod] = useState<string>('1Y');

  const { data: overview, isLoading: overviewLoading, error: overviewError } = useQuery({
    queryKey: ['overview'],
    queryFn: async () => (await apiClient.get('/overview')).data
  });

  const { data: correlation, isLoading: corrLoading } = useQuery({
    queryKey: ['correlation'],
    queryFn: async () => (await apiClient.get('/correlation')).data
  });

  const { data: regimes, isLoading: regLoading } = useQuery({
    queryKey: ['regimes', 'BTC-USD'],
    queryFn: async () => (await apiClient.get('/regimes?asset=BTC-USD')).data
  });

  const assets = overview?.assets;
  const metrics = overview?.metrics;
  const prices = overview?.prices;
  
  const assetKeys = useMemo(() => assets ? Object.keys(assets) : [], [assets]);
  const isSuccess = !!overview && assetKeys.length > 0;
  
  const isLoading = overviewLoading || corrLoading || regLoading;
  const error = overviewError;

  // Derive Market Pulse
  const pulse = useMemo(() => {
    if (!isSuccess) return { advancing: 0, declining: 0, avgRet: 0, avgVol: 0 };
    let adv = 0, dec = 0, sumRet = 0, sumVol = 0;
    assetKeys.forEach(k => {
      const m = metrics![k];
      if (m.cagr > 0.001) adv++;
      else if (m.cagr < -0.001) dec++;
      sumRet += m.cagr;
      sumVol += m.annualized_volatility;
    });
    return {
      advancing: adv,
      declining: dec,
      avgRet: sumRet / assetKeys.length,
      avgVol: sumVol / assetKeys.length
    };
  }, [isSuccess, metrics, assetKeys]);

  // Derived Chart Data (Rebased)
  const chartData = useMemo(() => {
    if (!isSuccess || !prices) return [];
    
    let latestDateStr = "";
    assetKeys.forEach(k => {
      const dates = prices[k]?.dates;
      if (dates && dates.length > 0) {
        const last = dates[dates.length - 1];
        if (last > latestDateStr) latestDateStr = last;
      }
    });
    
    if (!latestDateStr) return [];
    const latestDate = new Date(latestDateStr);
    
    let cutoff = new Date(latestDate);
    if (chartPeriod === '1M') cutoff.setMonth(cutoff.getMonth() - 1);
    else if (chartPeriod === '3M') cutoff.setMonth(cutoff.getMonth() - 3);
    else if (chartPeriod === '6M') cutoff.setMonth(cutoff.getMonth() - 6);
    else if (chartPeriod === '1Y') cutoff.setFullYear(cutoff.getFullYear() - 1);
    else if (chartPeriod === 'MAX') cutoff = new Date("1900-01-01");
    const cutoffStr = cutoff.toISOString().split('T')[0];

    return assetKeys.map(key => {
      const p = prices[key];
      const a = assets![key];
      if (!p || !p.dates.length) return null;
      
      let startIndex = 0;
      for (let i = 0; i < p.dates.length; i++) {
        if (p.dates[i] >= cutoffStr) {
          startIndex = i;
          break;
        }
      }
      
      const filteredDates = p.dates.slice(startIndex);
      const baseVal = p.rebased[startIndex] || 1;
      const filteredRebased = p.rebased.slice(startIndex).map((v: number) => (v / baseVal) * 100);
      
      return {
        x: filteredDates,
        y: filteredRebased,
        type: 'scatter',
        mode: 'lines',
        name: a.name,
        line: { width: 2, color: key === 'BTC-USD' ? '#FBBF24' : (key === 'NVDA' ? '#089958' : (key === 'GC=F' ? '#F59E0B' : undefined)) }
      };
    }).filter(Boolean) as any[];
  }, [isSuccess, prices, assets, assetKeys, chartPeriod]);

  // Top Movers
  const topMovers = useMemo(() => {
    if (!isSuccess) return [];
    const arr = assetKeys.map(k => ({
      key: k,
      name: assets![k].name,
      cagr: metrics![k].cagr,
      vol: metrics![k].annualized_volatility,
      dd: metrics![k].max_drawdown
    }));
    return arr.sort((a, b) => b.cagr - a.cagr);
  }, [isSuccess, metrics, assetKeys, assets]);

  // Scatter plot data
  const scatterData = useMemo(() => {
    if (!isSuccess) return [];
    return [{
      x: assetKeys.map(k => metrics![k].annualized_volatility * 100),
      y: assetKeys.map(k => metrics![k].cagr * 100),
      text: assetKeys.map(k => assets![k].name),
      mode: 'markers+text',
      type: 'scatter',
      textposition: 'top center',
      marker: { size: 10, color: '#089958', line: { width: 1, color: '#067A46' } },
      hoverinfo: 'text+x+y'
    }];
  }, [isSuccess, metrics, assetKeys, assets]);

  // Research Signals
  const researchSignals = useMemo(() => {
    if (!isSuccess) return [];
    const signals = [];
    if (topMovers.length > 0) {
      signals.push({ type: 'momentum', title: 'Strong Momentum', text: `${topMovers[0].name} leads with ${pct(topMovers[0].cagr)} annualized return.` });
    }
    const maxDdAsset = [...topMovers].sort((a, b) => a.dd - b.dd)[0]; // Lowest is worst drawdown (negative)
    if (maxDdAsset) {
      signals.push({ type: 'drawdown', title: 'Large Drawdown', text: `${maxDdAsset.name} is currently experiencing a ${pct(maxDdAsset.dd)} drawdown.` });
    }
    const minVolAsset = [...topMovers].sort((a, b) => a.vol - b.vol)[0];
    if (minVolAsset) {
      signals.push({ type: 'volatility', title: 'Low Volatility', text: `${minVolAsset.name} presents the most stable profile (${pct(minVolAsset.vol)}).` });
    }
    return signals;
  }, [topMovers, isSuccess]);

  // Priority Cards
  const priorityTickers = ["GC=F", "BTC-USD", "NVDA"];

  return (
    <div className="space-y-8 flex flex-col h-full animate-fade-in p-4 md:p-8 max-w-[1600px] mx-auto">
      
      {/* HEADER */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end border-b border-border pb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-text-main">Quantitative Market Intelligence</h1>
          <p className="text-sm text-text-muted mt-2 max-w-2xl">Multi-asset performance, risk metrics, and market structure analysis using historical time series data.</p>
        </div>
        <div className="mt-4 md:mt-0 flex items-center gap-4">
          <div className="flex gap-2 text-text-muted">
            <button className="p-2 hover:bg-surface-hover rounded-full transition-colors"><Search size={18} /></button>
            <button className="p-2 hover:bg-surface-hover rounded-full transition-colors"><Bell size={18} /></button>
          </div>
          <div className="h-6 w-px bg-border mx-2"></div>
          <div className="flex gap-3">
            <Badge variant="outline" className="px-3 py-1.5 text-[11px] font-mono border-border bg-surface">
              <Database size={12} className="mr-2 inline text-primary" /> Data: Connected
            </Badge>
            <Badge variant="outline" className="px-3 py-1.5 text-[11px] font-mono border-border bg-surface">
              <Calendar size={12} className="mr-2 inline text-primary" /> As of: {isSuccess && prices ? prices[assetKeys[0]]?.provenance.last_bar : 'Loading'}
            </Badge>
          </div>
        </div>
      </div>

      <QueryStateWrapper
        isLoading={isLoading}
        error={error}
        data={isSuccess ? { assets } : undefined}
        onRetry={() => {}} 
      >
        {() => (
          <>
            {/* ASSET INTELLIGENCE CARDS */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
              {priorityTickers.map(ticker => {
                const metric = metrics?.[ticker];
                const assetConfig = assets?.[ticker];
                if (!metric || !assetConfig) return null;
                const isPos = metric.cagr >= 0;
                
                return (
                  <Card key={ticker} className="hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden relative group" onClick={() => navigate('/explorer', { state: { asset: ticker } })}>
                    <div className={`absolute top-0 left-0 w-full h-1 ${isPos ? 'bg-positive' : 'bg-negative'} opacity-80`}></div>
                    <CardContent className="p-5">
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <h3 className="text-sm font-bold text-text-main">{assetConfig.name}</h3>
                          <div className="text-[10px] uppercase font-bold text-text-muted tracking-wider mt-0.5">{ticker} &bull; {assetConfig.asset_class || 'Asset'}</div>
                        </div>
                        <div className={`p-1.5 rounded-full ${isPos ? 'bg-positive/10 text-positive' : 'bg-negative/10 text-negative'}`}>
                          {isPos ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
                        </div>
                      </div>
                      <div className="text-3xl font-mono font-bold tracking-tight mb-4">
                        {metric.current_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                      </div>
                      
                      <div className="grid grid-cols-2 gap-y-3 gap-x-2 text-xs">
                        <div>
                          <div className="text-text-muted mb-1 text-[10px] uppercase font-bold tracking-wider">CAGR</div>
                          <div className={`font-mono font-medium ${isPos ? 'text-positive' : 'text-negative'}`}>{pct(metric.cagr)}</div>
                        </div>
                        <div>
                          <div className="text-text-muted mb-1 text-[10px] uppercase font-bold tracking-wider">Sharpe</div>
                          <div className="font-mono font-medium">{metric.sharpe.toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-text-muted mb-1 text-[10px] uppercase font-bold tracking-wider">Volatility</div>
                          <div className="font-mono font-medium">{pct(metric.annualized_volatility)}</div>
                        </div>
                        <div>
                          <div className="text-text-muted mb-1 text-[10px] uppercase font-bold tracking-wider">Max DD</div>
                          <div className="font-mono font-medium text-negative">{pct(metric.max_drawdown)}</div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}

              {/* Market Pulse Card */}
              <Card className="bg-surface-hover border-border relative overflow-hidden">
                <CardContent className="p-5 h-full flex flex-col justify-between">
                  <div>
                    <div className="flex items-center text-text-main mb-1">
                      <Activity size={18} className="mr-2 text-primary" />
                      <h3 className="text-sm font-bold">Market Pulse</h3>
                    </div>
                    <p className="text-[10px] uppercase font-bold text-text-muted tracking-wider">Aggregate Tracked Universe</p>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-y-4 gap-x-2 text-xs mt-4">
                    <div>
                      <div className="text-text-muted mb-1 text-[10px] uppercase font-bold tracking-wider">Advancing</div>
                      <div className="font-mono font-bold text-positive text-lg">{pulse.advancing}</div>
                    </div>
                    <div>
                      <div className="text-text-muted mb-1 text-[10px] uppercase font-bold tracking-wider">Declining</div>
                      <div className="font-mono font-bold text-negative text-lg">{pulse.declining}</div>
                    </div>
                    <div>
                      <div className="text-text-muted mb-1 text-[10px] uppercase font-bold tracking-wider">Avg Return</div>
                      <div className={`font-mono font-bold ${pulse.avgRet >= 0 ? 'text-positive' : 'text-negative'}`}>{pct(pulse.avgRet)}</div>
                    </div>
                    <div>
                      <div className="text-text-muted mb-1 text-[10px] uppercase font-bold tracking-wider">Avg Volatility</div>
                      <div className="font-mono font-bold">{pct(pulse.avgVol)}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* MAIN DASHBOARD GRID */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              
              {/* Relative Performance */}
              <Card className="xl:col-span-2 min-h-[450px] flex flex-col shadow-sm">
                <CardHeader className="flex flex-row items-center justify-between py-4 border-b border-border/50">
                  <CardTitle className="text-sm flex items-center">
                    <TrendingUp size={16} className="text-primary mr-2" />
                    Relative Performance
                  </CardTitle>
                  <div className="flex gap-1 bg-surface-highlight/50 p-1 rounded-md">
                    {['1M', '3M', '6M', '1Y', 'MAX'].map(p => (
                      <button
                        key={p}
                        onClick={() => setChartPeriod(p)}
                        className={`px-3 py-1 text-xs font-bold rounded ${chartPeriod === p ? 'bg-surface shadow-sm text-primary' : 'text-text-muted hover:text-text-main'}`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </CardHeader>
                <div className="flex-1 w-full p-2">
                  <Plot
                    data={chartData}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 20, r: 20, l: 40, b: 40 },
                      xaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true, tickfont: { family: 'Inter', size: 10 } },
                      yaxis: { color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true, tickfont: { family: 'Inter', size: 10 } },
                      legend: { orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "right", x: 1, font: { family: 'Inter', size: 10, color: 'var(--text-main)' } },
                      hovermode: 'x unified'
                    }}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </Card>

              {/* Research Signals & Regimes */}
              <div className="flex flex-col gap-6">
                <Card className="shadow-sm">
                  <CardHeader className="py-4 border-b border-border/50">
                    <CardTitle className="text-sm flex items-center">
                      <Layers size={16} className="text-primary mr-2" />
                      Market Regime (Proxy: BTC)
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4">
                    {regLoading ? (
                       <div className="h-20 flex items-center justify-center"><div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div></div>
                    ) : regimes ? (
                       <div className="grid grid-cols-2 gap-4">
                          <div className="bg-surface-hover rounded-md p-4 flex flex-col items-center justify-center border border-border/50">
                            <span className="text-[10px] uppercase font-bold text-text-muted tracking-wider mb-2">Trend</span>
                            <Badge variant={regimes.bull_bear[regimes.bull_bear.length-1] > 0 ? "positive" : "negative"} className="px-3 py-1">
                              {regimes.bull_bear[regimes.bull_bear.length-1] > 0 ? "BULLISH" : "BEARISH"}
                            </Badge>
                          </div>
                          <div className="bg-surface-hover rounded-md p-4 flex flex-col items-center justify-center border border-border/50">
                            <span className="text-[10px] uppercase font-bold text-text-muted tracking-wider mb-2">Volatility</span>
                            <Badge variant={regimes.volatility[regimes.volatility.length-1] > 0 ? "warning" : "default"} className="px-3 py-1">
                              {regimes.volatility[regimes.volatility.length-1] > 0 ? "HIGH VOL" : "LOW VOL"}
                            </Badge>
                          </div>
                       </div>
                    ) : (
                       <div className="text-xs text-text-muted">Regime data unavailable.</div>
                    )}
                  </CardContent>
                </Card>

                <Card className="flex-1 shadow-sm">
                  <CardHeader className="py-4 border-b border-border/50">
                    <CardTitle className="text-sm flex items-center">
                      <AlertTriangle size={16} className="text-warning mr-2" />
                      Research Signals
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4 space-y-3">
                    {researchSignals.map((sig, i) => (
                      <div key={i} className="flex items-start p-3 bg-surface-hover rounded-md border border-border/50 transition-colors hover:border-border">
                        <div className={`mt-0.5 mr-3 w-2 h-2 rounded-full shrink-0 ${sig.type === 'momentum' ? 'bg-positive' : (sig.type === 'drawdown' ? 'bg-negative' : 'bg-primary')}`}></div>
                        <div>
                          <h4 className="text-[11px] uppercase font-bold text-text-main mb-1 tracking-wider">{sig.title}</h4>
                          <p className="text-xs text-text-muted leading-relaxed">{sig.text}</p>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>
            </div>
            
            {/* LOWER GRID */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              
              {/* Risk / Return Map */}
              <Card className="xl:col-span-1 min-h-[350px] flex flex-col shadow-sm">
                <CardHeader className="py-4 border-b border-border/50">
                  <CardTitle className="text-sm flex items-center">
                    <LayoutGrid size={16} className="text-primary mr-2" />
                    Risk / Return Map
                  </CardTitle>
                </CardHeader>
                <div className="flex-1 w-full p-2">
                  <Plot
                    data={scatterData}
                    layout={{
                      autosize: true,
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      margin: { t: 30, r: 30, l: 40, b: 40 },
                      xaxis: { title: 'Volatility (%)', color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true, tickfont: { family: 'Inter', size: 10 }, titlefont: { size: 10, family: 'Inter' } },
                      yaxis: { title: 'Return (%)', color: 'var(--text-muted)', gridcolor: 'var(--border-color)', showgrid: true, tickfont: { family: 'Inter', size: 10 }, titlefont: { size: 10, family: 'Inter' } },
                      hovermode: 'closest'
                    }}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </Card>

              {/* Top Movers */}
              <Card className="xl:col-span-1 shadow-sm">
                <CardHeader className="py-4 border-b border-border/50">
                  <CardTitle className="text-sm flex items-center">
                    <TrendingUp size={16} className="text-primary mr-2" />
                    Top Movers
                  </CardTitle>
                </CardHeader>
                <div className="overflow-x-auto p-0">
                  <table className="w-full text-left">
                    <thead className="text-[10px] uppercase text-text-muted bg-surface-hover/50 border-b border-border">
                      <tr>
                        <th className="py-3 px-4 font-bold tracking-wider">Asset</th>
                        <th className="py-3 px-4 font-bold tracking-wider text-right">Return</th>
                        <th className="py-3 px-4 font-bold tracking-wider text-right">Vol</th>
                        <th className="py-3 px-4 font-bold tracking-wider text-right">DD</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50 text-xs">
                      {topMovers.slice(0, 7).map(item => (
                        <tr key={item.key} className="hover:bg-surface-highlight/30 transition-colors">
                          <td className="py-3 px-4 font-medium text-text-main">{item.key}</td>
                          <td className={`py-3 px-4 text-right font-mono font-medium ${item.cagr >= 0 ? 'text-positive' : 'text-negative'}`}>{pct(item.cagr)}</td>
                          <td className="py-3 px-4 text-right font-mono text-text-muted">{pct(item.vol)}</td>
                          <td className="py-3 px-4 text-right font-mono text-negative">{pct(item.dd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              {/* Correlation & Data Quality */}
              <div className="flex flex-col gap-6">
                <Card className="shadow-sm flex-1">
                  <CardHeader className="py-4 border-b border-border/50 flex flex-row items-center justify-between">
                    <CardTitle className="text-sm flex items-center">
                      <Network size={16} className="text-primary mr-2" />
                      Correlation Snapshot
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4 flex flex-col justify-center items-center h-full">
                    {corrLoading ? (
                      <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                    ) : correlation ? (
                       <div className="w-full space-y-2">
                         <div className="grid grid-cols-4 gap-1 text-[10px] font-bold text-text-muted uppercase text-center mb-2">
                           <div></div>
                           <div className="truncate">BTC</div>
                           <div className="truncate">NVDA</div>
                           <div className="truncate">GLD</div>
                         </div>
                         <div className="bg-surface-hover rounded-md border border-border p-6 flex flex-col items-center text-center">
                           <Network size={32} className="text-border mb-3" />
                           <p className="text-xs text-text-muted mb-4 max-w-[200px]">Matrix generated for {correlation.assets?.length || 0} assets across the selected universe.</p>
                           <button onClick={() => navigate('/correlation')} className="btn-secondary w-full text-xs py-2 rounded-full cursor-pointer">View Full Risk Analysis</button>
                         </div>
                       </div>
                    ) : (
                      <div className="text-xs text-text-muted">Correlation unavailable.</div>
                    )}
                  </CardContent>
                </Card>

                <Card className="shadow-sm">
                  <CardHeader className="py-3 border-b border-border/50">
                    <CardTitle className="text-sm flex items-center">
                      <ShieldCheck size={16} className="text-primary mr-2" />
                      Data Quality
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4">
                    <div className="space-y-3 text-xs">
                      <div className="flex justify-between items-center">
                        <span className="text-text-muted font-medium">Source Database</span>
                        <Badge variant="outline" className="font-mono text-[10px] border-border bg-surface">Supabase</Badge>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-text-muted font-medium">Earliest Record</span>
                        <span className="font-mono text-text-main font-medium">{prices ? prices[assetKeys[0]]?.provenance.first_bar : '-'}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-text-muted font-medium">Tracked Assets</span>
                        <span className="font-mono text-text-main font-medium">{assetKeys.length}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-text-muted font-medium">System Health</span>
                        <Badge variant="positive" className="text-[10px]">OPERATIONAL</Badge>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

            </div>
          </>
        )}
      </QueryStateWrapper>
    </div>
  );
}
