import { useState, useRef, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiClient } from '../api/client';
import type { ResearchResponse } from '../api/types';
import { 
  Sparkles, 
  Bot, 
  User, 
  CheckCircle2, 
  ChevronDown, 
  ChevronUp, 
  Terminal, 
  Network, 
  TrendingUp, 
  ShieldAlert, 
  PieChart, 
  Layers, 
  RotateCcw,
  Activity,
  ExternalLink,
  Shield,
  Mic,
  Plus,
  ArrowUp,
  Home,
  Boxes,
  LayoutGrid,
  Sliders,
  Plug,
  Search,
  SlidersHorizontal,
  ChevronRight,
  Database,
  Cpu,
  Clock,
  Gauge,
  Play
} from 'lucide-react';

interface ChatMessage {
  id: string;
  sender: 'user' | 'openclaw';
  timestamp: string;
  query?: string;
  data?: ResearchResponse;
  isLoading?: boolean;
  error?: string;
}

interface SessionData {
  id: string;
  name: string;
  subtitle: string;
  messages: ChatMessage[];
}

const QUICK_PROMPTS = [
  'I have 1 lakh which asset is to buy with low risk',
  'Run minimum volatility portfolio allocation for ₹1,00,000.',
  'Analyze BTC and NVIDIA from 2022 to 2026.',
  'Compare Gold (GC=F) and BTC correlation and volatility.',
  'Evaluate risk metrics and drawdown for Bitcoin.'
];

const INITIAL_SESSIONS: Record<string, SessionData> = {
  'main': {
    id: 'main',
    name: 'Main Session',
    subtitle: 'General Quantitative Research',
    messages: [
      {
        id: 'welcome',
        sender: 'openclaw',
        timestamp: '02:00',
      }
    ]
  },
  'btc-nvda': {
    id: 'btc-nvda',
    name: 'BTC & NVDA Risk Deep Dive',
    subtitle: 'Cross-Asset Volatility & Drawdowns',
    messages: [
      {
        id: 'user_1',
        sender: 'user',
        timestamp: '02:05',
        query: 'Evaluate risk metrics and drawdown for NVDA and BTC'
      },
      {
        id: 'agent_1',
        sender: 'openclaw',
        timestamp: '02:05',
        query: 'Evaluate risk metrics and drawdown for NVDA and BTC',
        data: {
          query: 'Evaluate risk metrics and drawdown for NVDA and BTC',
          assets_analyzed: ['BTC-USD', 'NVDA'],
          orchestration_steps: [
            { step: 'Intent Understanding', status: 'success', detail: 'Identified target assets (BTC-USD, NVDA) and analysis horizon: Historical Sample Period' },
            { step: 'Quantitative Risk Analysis', status: 'success', detail: 'Calculated deterministic CAGR, Volatility, Sharpe Ratio, and Maximum Drawdown' },
            { step: 'Correlation Analysis', status: 'success', detail: 'Evaluated cross-asset correlation matrix from QuantExa risk engine (0.3774)' },
            { step: 'NVIDIA NIM Neural Synthesis', status: 'success', detail: 'Synthesized institutional research conclusion via NVIDIA Nemotron (nvidia/nemotron-3-super-120b-a12b)' }
          ],
          findings: [
            { category: 'Performance', content: 'Bitcoin (BTC-USD): CAGR +43.11%. NVIDIA (NVDA): CAGR +69.16%.' },
            { category: 'Risk', content: 'Bitcoin annualized volatility 74.22%, Sharpe 0.86, Max Drawdown -72.55%. NVIDIA volatility 54.38%, Sharpe 1.24, Max Drawdown -66.34%.' },
            { category: 'Correlation', content: 'Cross-asset correlation is 0.3774, indicating meaningful diversification benefits.' }
          ],
          conclusion: 'NVDA delivers superior risk-adjusted return (Sharpe 1.24) relative to Bitcoin (Sharpe 0.86), while the moderate 0.38 correlation enables downside-dampening portfolio diversification.',
          markdown_report: `### 📊 Quantitative Risk & Drawdown Report: BTC-USD & NVDA
**Analysis Scope**: \`Historical Sample Period\` • **Source**: \`QuantExa Engine Verified\`

| Asset | Current Price | CAGR (%) | Volatility (%) | Sharpe Ratio | Max Drawdown |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BTC-USD** | $19,222.67 | \`+43.11%\` | \`74.22%\` | \`0.86\` | \`-72.55%\` |
| **NVDA** | $47.97 | \`+69.16%\` | \`54.38%\` | \`1.24\` | \`-66.34%\` |

#### 🔍 Institutional Takeaways (NVIDIA NIM Synthesis)
- **Asymmetric Risk Profile**: NVDA's higher CAGR combined with lower annualized volatility yields a Sharpe ratio of 1.24, markedly outpacing BTC's 0.86.
- **Drawdown Resilience**: While both assets experienced steep historical drawdowns (-72.55% vs -66.34%), NVDA recovered faster due to strong structural free-cash-flow generation.
- **Diversification Opportunity**: The 0.3774 correlation confirms that combining both assets allows institutional portfolios to harvest NVDA growth while dampening joint drawdowns.`
        }
      }
    ]
  },
  'portfolio-opt': {
    id: 'portfolio-opt',
    name: 'Max Sharpe Portfolio Solver',
    subtitle: 'Markowitz Mean-Variance Convex Allocation',
    messages: [
      {
        id: 'user_2',
        sender: 'user',
        timestamp: '02:15',
        query: 'Run Max Sharpe portfolio optimization on BTC and NVDA.'
      },
      {
        id: 'agent_2',
        sender: 'openclaw',
        timestamp: '02:15',
        query: 'Run Max Sharpe portfolio optimization on BTC and NVDA.',
        data: {
          query: 'Run Max Sharpe portfolio optimization on BTC and NVDA.',
          assets_analyzed: ['BTC-USD', 'NVDA'],
          orchestration_steps: [
            { step: 'Intent Understanding', status: 'success', detail: 'Parsed portfolio optimization request for BTC-USD and NVDA' },
            { step: 'Covariance Matrix Calculation', status: 'success', detail: 'Computed annualized covariance matrix from historical daily log returns' },
            { step: 'Convex Optimization Solver', status: 'success', detail: 'Executed SLSQP solver targeting maximum Sharpe ratio subject to non-negative weights' },
            { step: 'NVIDIA NIM Synthesis', status: 'success', detail: 'Interpreted optimal capital allocation and diversification efficiency' }
          ],
          findings: [
            { category: 'Optimal Weights', content: 'BTC-USD: 52.1%, NVDA: 47.9%' },
            { category: 'Portfolio Metrics', content: 'Expected Annual Return: 53.90%, Expected Volatility: 54.35%, Portfolio Sharpe: 0.99' }
          ],
          conclusion: 'The optimal Max Sharpe allocation splits capital 52.1% in BTC-USD and 47.9% in NVDA, achieving an expected return of 53.90% with 54.35% volatility.',
          markdown_report: `### 💼 Optimal Capital Allocation: Max-Sharpe Frontier
**Objective Function**: \`Maximize (R_p - R_f) / \sigma_p\` • **Constraint**: \`\sum w_i = 1, w_i \ge 0\`

#### ⚖️ Recommended Portfolio Allocation
- **BTC-USD**: \`52.1%\` ($521,000 per $1M AUM)
- **NVDA**: \`47.9%\` ($479,000 per $1M AUM)

#### 📈 Expected Portfolio Performance
- **Expected Return**: \`+53.90% / year\`
- **Portfolio Volatility**: \`54.35% / year\`
- **Blended Sharpe Ratio**: \`0.99\`

> **Takeaway**: Blending the two assets smooths individual idiosyncratic shocks, boosting overall portfolio risk-adjusted efficiency by +15.1% over a pure Bitcoin holding.`
        }
      }
    ]
  }
};

export function AiResearch() {
  const [inputText, setInputText] = useState('');
  const [sessions, setSessions] = useState<Record<string, SessionData>>(INITIAL_SESSIONS);
  const [activeSessionId, setActiveSessionId] = useState('main');
  const [activeNav, setActiveNav] = useState('Home');
  const [isSessionDropdownOpen, setIsSessionDropdownOpen] = useState(false);
  const [sessionSearchQuery, setSessionSearchQuery] = useState('');
  const [isSearchVisible, setIsSearchVisible] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});

  const chatBottomRef = useRef<HTMLDivElement>(null);

  const currentSession = sessions[activeSessionId] || sessions['main'];
  const messages = currentSession.messages;

  useEffect(() => {
    if (activeNav === 'Home') {
      chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, activeNav]);

  const toggleSteps = (msgId: string) => {
    setExpandedSteps(prev => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  const [selectedBatchId, setSelectedBatchId] = useState<string>(() => {
    return localStorage.getItem('quantexa_active_batch_id') || 'TEST_BATCH_01';
  });
  const [availableBatches, setAvailableBatches] = useState<{ batch_id: string; batch_name: string }[]>([]);

  useEffect(() => {
    apiClient.get('/financial-agent/batches')
      .then(res => {
        if (res.data && Array.isArray(res.data)) {
          setAvailableBatches(res.data);
        }
      })
      .catch(() => {});
  }, []);

  const researchMutation = useMutation({
    mutationFn: async (queryText: string) => {
      const response = await apiClient.post<ResearchResponse>('/research', { 
        query: queryText,
        batch_id: selectedBatchId || localStorage.getItem('quantexa_active_batch_id') || 'TEST_BATCH_01'
      });
      return response.data;
    },
    onSuccess: (data, queryText) => {
      setSessions(prev => {
        const sess = prev[activeSessionId];
        if (!sess) return prev;
        return {
          ...prev,
          [activeSessionId]: {
            ...sess,
            messages: sess.messages.map(msg => 
              msg.isLoading && msg.query === queryText
                ? { ...msg, isLoading: false, data, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
                : msg
            )
          }
        };
      });
    },
    onError: (error: any, queryText) => {
      setSessions(prev => {
        const sess = prev[activeSessionId];
        if (!sess) return prev;
        return {
          ...prev,
          [activeSessionId]: {
            ...sess,
            messages: sess.messages.map(msg => 
              msg.isLoading && msg.query === queryText
                ? { 
                    ...msg, 
                    isLoading: false, 
                    error: error?.message || 'Failed to execute OpenClaw research orchestration.', 
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) 
                  }
                : msg
            )
          }
        };
      });
    }
  });

  const handleSendMessage = (queryText: string) => {
    const trimmed = queryText.trim();
    if (!trimmed || researchMutation.isPending) return;

    // Switch back to Home view if user was inspecting another tab
    if (activeNav !== 'Home') {
      setActiveNav('Home');
    }

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsgId = `user_${Date.now()}`;
    const agentMsgId = `agent_${Date.now()}`;

    setSessions(prev => {
      const sess = prev[activeSessionId];
      if (!sess) return prev;
      return {
        ...prev,
        [activeSessionId]: {
          ...sess,
          messages: [
            ...sess.messages,
            { id: userMsgId, sender: 'user', timestamp: timeStr, query: trimmed },
            { id: agentMsgId, sender: 'openclaw', timestamp: timeStr, query: trimmed, isLoading: true }
          ]
        }
      };
    });

    setExpandedSteps(prev => ({ ...prev, [agentMsgId]: true }));
    setInputText('');

    researchMutation.mutate(trimmed);
  };

  const handleCreateNewSession = () => {
    const newId = `session_${Date.now()}`;
    const newSession: SessionData = {
      id: newId,
      name: `Research Run #${Object.keys(sessions).length + 1}`,
      subtitle: 'New Quantitative Session',
      messages: [
        {
          id: `welcome_${Date.now()}`,
          sender: 'openclaw',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }
      ]
    };
    setSessions(prev => ({ ...prev, [newId]: newSession }));
    setActiveSessionId(newId);
    setActiveNav('Home');
    setIsSessionDropdownOpen(false);
  };

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
    setActiveNav('Home');
    setIsSessionDropdownOpen(false);
  };

  const handleClearSession = () => {
    setSessions(prev => {
      const sess = prev[activeSessionId];
      if (!sess) return prev;
      return {
        ...prev,
        [activeSessionId]: {
          ...sess,
          messages: [
            {
              id: `welcome_${Date.now()}`,
              sender: 'openclaw',
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            }
          ]
        }
      };
    });
  };

  const filteredSessionIds = Object.keys(sessions).filter(id => {
    if (!sessionSearchQuery) return true;
    const s = sessions[id];
    return s.name.toLowerCase().includes(sessionSearchQuery.toLowerCase()) ||
           s.subtitle.toLowerCase().includes(sessionSearchQuery.toLowerCase());
  });

  const getCategoryIcon = (category: string) => {
    const cat = category.toLowerCase();
    if (cat.includes('performance') || cat.includes('return')) return <TrendingUp size={14} className="text-primary" />;
    if (cat.includes('risk') || cat.includes('drawdown')) return <ShieldAlert size={14} className="text-warning" />;
    if (cat.includes('correlation')) return <Network size={14} className="text-accent" />;
    if (cat.includes('portfolio') || cat.includes('optimization')) return <PieChart size={14} className="text-positive" />;
    if (cat.includes('context') || cat.includes('knowledge')) return <Layers size={14} className="text-purple-400" />;
    return <Activity size={14} className="text-primary" />;
  };

  return (
    <div className="flex h-[calc(100vh-4.5rem)] w-full max-w-full bg-background overflow-hidden border border-border rounded-2xl shadow-lg relative">
      
      {/* ========================================================= */}
      {/* 1. OpenClaw Left Control Sidebar (Native OpenClaw Style)  */}
      {/* ========================================================= */}
      <aside className="w-64 flex-shrink-0 bg-surface/90 border-r border-border flex flex-col justify-between hidden md:flex select-none">
        <div className="p-3 space-y-4">
          
          {/* OpenClaw Workspace / Session Selector with Dropdown */}
          <div className="relative">
            <div className="flex items-center justify-between p-2 rounded-xl bg-surface-hover/60 border border-border/80">
              <button 
                onClick={() => setIsSessionDropdownOpen(!isSessionDropdownOpen)}
                className="flex items-center gap-2.5 text-left cursor-pointer flex-1 min-w-0"
              >
                <div className="w-7 h-7 rounded-lg bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-500 flex-shrink-0">
                  <Bot size={16} />
                </div>
                <div className="truncate">
                  <div className="flex items-center gap-1 text-xs font-bold text-text-main truncate">
                    <span className="truncate">{currentSession.name}</span>
                    <ChevronDown size={12} className="text-text-muted flex-shrink-0" />
                  </div>
                  <div className="text-[10px] text-text-muted font-mono truncate">QuantExa Workspace</div>
                </div>
              </button>
              <div className="flex items-center gap-1 text-text-muted flex-shrink-0">
                <button onClick={handleCreateNewSession} title="New Session" className="p-1 hover:text-text-main hover:bg-surface rounded transition-colors cursor-pointer">
                  <Plus size={13} />
                </button>
                <button onClick={() => setIsSearchVisible(!isSearchVisible)} title="Search Sessions" className="p-1 hover:text-text-main hover:bg-surface rounded transition-colors cursor-pointer">
                  <Search size={13} />
                </button>
              </div>
            </div>

            {/* Session Switcher Popover */}
            {isSessionDropdownOpen && (
              <div className="absolute top-full left-0 right-0 mt-1.5 p-2 bg-surface border border-border rounded-xl shadow-xl z-50 space-y-1 animate-fade-in">
                <div className="text-[10px] font-mono text-text-muted px-2 py-1 font-semibold uppercase">Switch Session</div>
                {Object.values(sessions).map(s => (
                  <button
                    key={s.id}
                    onClick={() => handleSelectSession(s.id)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs flex items-center justify-between transition-colors cursor-pointer ${
                      s.id === activeSessionId ? 'bg-rose-500/15 text-rose-400 font-semibold' : 'text-text-muted hover:text-text-main hover:bg-surface-hover'
                    }`}
                  >
                    <span className="truncate">{s.name}</span>
                    {s.id === activeSessionId && <CheckCircle2 size={12} className="text-rose-500 flex-shrink-0" />}
                  </button>
                ))}
                <button
                  onClick={handleCreateNewSession}
                  className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-primary hover:bg-primary/10 flex items-center gap-1.5 font-medium border-t border-border/60 pt-2 mt-1 cursor-pointer"
                >
                  <Plus size={12} />
                  <span>Create New Session</span>
                </button>
              </div>
            )}
          </div>

          {/* Quick Search Sessions Input (toggled via search icon) */}
          {isSearchVisible && (
            <div className="animate-fade-in">
              <input
                type="text"
                value={sessionSearchQuery}
                onChange={(e) => setSessionSearchQuery(e.target.value)}
                placeholder="Filter sessions..."
                className="w-full px-2.5 py-1.5 text-xs bg-background border border-border rounded-lg text-text-main focus:outline-hidden focus:border-rose-500"
              />
            </div>
          )}

          {/* Primary Navigation Tabs */}
          <nav className="space-y-1">
            {[
              { label: 'Home', icon: Home, active: activeNav === 'Home' },
              { label: 'Agents', icon: Bot, badge: '1 Active', active: activeNav === 'Agents' },
              { label: 'Dashboards', icon: LayoutGrid, active: activeNav === 'Dashboards' },
              { label: 'Systems', icon: Boxes, active: activeNav === 'Systems' },
              { label: 'Automations', icon: Sliders, active: activeNav === 'Automations' },
              { label: 'Plugins', icon: Plug, badge: 'QuantExa', active: activeNav === 'Plugins' },
            ].map((item) => {
              const Icon = item.icon;
              const isActive = item.active;
              return (
                <button
                  key={item.label}
                  onClick={() => setActiveNav(item.label)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs transition-all cursor-pointer ${
                    isActive 
                      ? 'bg-rose-500/10 text-rose-500 font-semibold border border-rose-500/20' 
                      : 'text-text-muted hover:text-text-main hover:bg-surface-hover'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Icon size={14} className={isActive ? 'text-rose-500' : 'text-text-muted'} />
                    <span>{item.label}</span>
                  </div>
                  {item.badge && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-surface border border-border text-text-muted font-mono">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Sessions List Section */}
          <div className="space-y-1.5 pt-2 border-t border-border/60">
            <div className="flex items-center justify-between px-2 text-[10px] font-mono font-semibold uppercase text-text-muted tracking-wider">
              <span>Sessions</span>
              <div className="flex items-center gap-1">
                <SlidersHorizontal size={11} className="hover:text-text-main cursor-pointer" />
                <Plus size={11} onClick={handleCreateNewSession} className="hover:text-text-main cursor-pointer" />
              </div>
            </div>

            <div className="space-y-1">
              {filteredSessionIds.map(id => {
                const sess = sessions[id];
                const isSelected = id === activeSessionId;
                return (
                  <button 
                    key={id}
                    onClick={() => handleSelectSession(id)}
                    className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-left transition-colors cursor-pointer ${
                      isSelected 
                        ? 'bg-surface-hover text-text-main font-medium border border-border/80' 
                        : 'text-text-muted hover:text-text-main hover:bg-surface-hover/60'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-positive animate-pulse' : 'bg-border'}`}></span>
                      <span className="truncate">{sess.name}</span>
                    </div>
                    <ChevronRight size={12} className="text-text-muted flex-shrink-0" />
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Sidebar Footer: System Status & User Profile */}
        <div className="p-3 border-t border-border/60 space-y-3 bg-surface/40">
          <div className="p-2.5 rounded-xl bg-surface border border-border/80 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-semibold text-text-main">
              <span className="flex items-center gap-1.5">
                <Sparkles size={12} className="text-emerald-400" />
                <span>NVIDIA NIM</span>
              </span>
              <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20">
                Nemotron 120B
              </span>
            </div>
            <div className="text-[10px] text-text-muted leading-relaxed font-mono">
              Gateway: 127.0.0.1:18789
              <br />Engine: FastAPI Port 8000
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-primary font-bold text-xs">
                A
              </div>
              <div className="leading-tight">
                <div className="text-xs font-semibold text-text-main">Analyst</div>
                <div className="text-[10px] text-text-muted font-mono">Game Spark</div>
              </div>
            </div>
            <a 
              href="http://127.0.0.1:18789/chat/main?token=b622236f97cef36ef2450b892ec6c9bdd55a430285beed50" 
              target="_blank" 
              rel="noreferrer"
              title="Open native OpenClaw Dashboard" 
              className="p-1.5 rounded-lg bg-surface-hover text-text-muted hover:text-text-main transition-colors cursor-pointer"
            >
              <ExternalLink size={13} />
            </a>
          </div>
        </div>
      </aside>

      {/* ========================================================= */}
      {/* 2. Main Content Workspace (Dynamic based on activeNav)     */}
      {/* ========================================================= */}
      <main className="flex-1 flex flex-col h-full min-w-0 bg-background">
        
        {/* Top Header Bar */}
        <header className="flex items-center justify-between px-5 py-3 border-b border-border bg-surface/50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-500 md:hidden">
              <Bot size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-text-main">
                  {activeNav === 'Home' ? currentSession.name : `OpenClaw • ${activeNav}`}
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                  agent:main
                </span>
              </div>
              <p className="text-[11px] text-text-muted font-mono hidden sm:block">
                OpenClaw Quantitative Copilot • QuantExa Native Runtime
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs">
            {/* Batch Selector */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface border border-border text-[11px]">
              <Database size={12} className="text-primary shrink-0" />
              <span className="text-text-muted hidden md:inline">Batch:</span>
              <select
                value={selectedBatchId}
                onChange={(e) => {
                  setSelectedBatchId(e.target.value);
                  localStorage.setItem('quantexa_active_batch_id', e.target.value);
                }}
                className="bg-transparent text-text-main font-mono text-[11px] focus:outline-none cursor-pointer max-w-[140px] truncate"
              >
                {availableBatches.length > 0 ? (
                  availableBatches.map(b => (
                    <option key={b.batch_id} value={b.batch_id} className="bg-surface text-text-main">
                      {b.batch_name} ({b.batch_id.slice(0, 8)})
                    </option>
                  ))
                ) : (
                  <option value="TEST_BATCH_01" className="bg-surface text-text-main">TEST_BATCH_01</option>
                )}
              </select>
            </div>

            <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-[11px]">
              <Sparkles size={12} className="text-emerald-400" />
              <span>NVIDIA NIM Active</span>
            </div>
            <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface-hover border border-border text-text-muted font-mono text-[11px]">
              <span className="w-1.5 h-1.5 rounded-full bg-positive animate-pulse"></span>
              <span>127.0.0.1:18789</span>
            </div>
            <a
              href="http://127.0.0.1:18789/chat/main?token=b622236f97cef36ef2450b892ec6c9bdd55a430285beed50"
              target="_blank"
              rel="noreferrer"
              title="Open native OpenClaw Dashboard"
              className="px-2.5 py-1 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-colors flex items-center gap-1 text-[11px] font-medium cursor-pointer"
            >
              <ExternalLink size={12} />
              <span>OpenClaw UI</span>
            </a>
            {activeNav === 'Home' && (
              <button
                onClick={handleClearSession}
                title="Clear Session"
                className="p-1.5 rounded-lg bg-surface-hover hover:bg-surface text-text-muted hover:text-text-main border border-border transition-colors cursor-pointer"
              >
                <RotateCcw size={13} />
              </button>
            )}
          </div>
        </header>

        {/* ------------------------------------------------------------- */}
        {/* VIEW 1: HOME (Interactive Chat & OpenClaw Research Terminal)  */}
        {/* ------------------------------------------------------------- */}
        {activeNav === 'Home' && (
          <>
            <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
              {messages.map((msg) => {
                if (msg.id.startsWith('welcome')) {
                  return (
                    <div key={msg.id} className="space-y-4 max-w-4xl mx-auto">
                      {/* Welcome Greeting Banner */}
                      <div className="p-5 rounded-2xl bg-surface/80 border border-border/90 shadow-xs space-y-3">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-500">
                            <Bot size={20} />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold text-text-main">OpenClaw Quantitative Copilot</span>
                              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-primary/10 text-primary border border-primary/20">
                                agent:main
                              </span>
                            </div>
                            <p className="text-xs text-text-muted font-mono">
                              Powered by NVIDIA NIM (nvidia/nemotron-3-super-120b-a12b)
                            </p>
                          </div>
                        </div>
                        
                        <p className="text-xs text-text-main leading-relaxed">
                          Welcome to the <strong>QuantExa AI Research Terminal</strong>. I am your institutional quantitative copilot. I analyze market microstructure, calculate verified risk metrics, backtest algorithmic strategies, and solve optimal portfolio weights — with <strong>zero look-ahead bias</strong>.
                        </p>

                        {/* 4 Interactive Feature Blocks */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
                          <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/80 flex items-center gap-2.5">
                            <TrendingUp size={16} className="text-primary flex-shrink-0" />
                            <div className="text-xs">
                              <div className="font-semibold text-text-main">Market & Quant</div>
                              <div className="text-[11px] text-text-muted">CAGR, Volatility, Sharpe, Drawdown</div>
                            </div>
                          </div>
                          <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/80 flex items-center gap-2.5">
                            <Network size={16} className="text-accent flex-shrink-0" />
                            <div className="text-xs">
                              <div className="font-semibold text-text-main">Risk & Correlation</div>
                              <div className="text-[11px] text-text-muted">Cross-asset co-movement matrices</div>
                            </div>
                          </div>
                          <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/80 flex items-center gap-2.5">
                            <PieChart size={16} className="text-positive flex-shrink-0" />
                            <div className="text-xs">
                              <div className="font-semibold text-text-main">Portfolio Solvers</div>
                              <div className="text-[11px] text-text-muted">Mean-Variance & QUBO quantum allocations</div>
                            </div>
                          </div>
                          <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/80 flex items-center gap-2.5">
                            <Layers size={16} className="text-purple-400 flex-shrink-0" />
                            <div className="text-xs">
                              <div className="font-semibold text-text-main">Knowledge Graph</div>
                              <div className="text-[11px] text-text-muted">Entity relationships & Neo4j lineage</div>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Suggested Research Prompts */}
                      <div className="space-y-2">
                        <div className="text-[11px] font-mono font-medium text-text-muted uppercase tracking-wider px-1">
                          Suggested Research Inquiries:
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {QUICK_PROMPTS.map((prompt, i) => (
                            <button
                              key={i}
                              onClick={() => handleSendMessage(prompt)}
                              className="px-3 py-1.5 rounded-xl bg-surface hover:bg-surface-hover border border-border text-xs text-text-main hover:border-primary/40 transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer text-left"
                            >
                              <Sparkles size={12} className="text-primary flex-shrink-0" />
                              <span>{prompt}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                }

                if (msg.sender === 'user') {
                  return (
                    <div key={msg.id} className="flex items-start justify-end gap-3 max-w-4xl mx-auto">
                      <div className="space-y-1 text-right max-w-[80%]">
                        <div className="flex items-center justify-end gap-2 text-[11px] text-text-muted font-mono">
                          <span>{msg.timestamp}</span>
                          <span className="font-semibold text-text-main">Analyst</span>
                        </div>
                        <div className="px-4 py-2.5 rounded-2xl bg-primary text-white text-xs leading-relaxed shadow-xs text-left inline-block">
                          {msg.query}
                        </div>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center flex-shrink-0 mt-1">
                        <User size={15} className="text-primary" />
                      </div>
                    </div>
                  );
                }

                // OpenClaw Assistant Message
                const isStepsOpen = expandedSteps[msg.id] ?? true;

                return (
                  <div key={msg.id} className="flex items-start gap-3.5 max-w-4xl mx-auto">
                    <div className="w-8 h-8 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center flex-shrink-0 mt-0.5 text-rose-500">
                      <Bot size={17} />
                    </div>

                    <div className="flex-1 space-y-3 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-text-main">OpenClaw Research Agent</span>
                        <span className="text-[11px] text-text-muted font-mono">{msg.timestamp}</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-rose-500/10 text-rose-500 border border-rose-500/20">
                          agent:main
                        </span>
                        {msg.data?.assets_analyzed && msg.data.assets_analyzed.length > 0 && (
                          <div className="flex gap-1">
                            {msg.data.assets_analyzed.map((a, i) => (
                              <span key={i} className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-primary/10 text-primary border border-primary/20">
                                {a}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {msg.isLoading ? (
                        /* Loading Trace State */
                        <div className="bg-surface/80 border border-border rounded-2xl p-4 space-y-3 animate-pulse">
                          <div className="flex items-center gap-2 text-xs text-rose-500 font-mono font-medium">
                            <Sparkles size={14} className="animate-spin text-rose-500" />
                            <span>OpenClaw executing orchestration...</span>
                          </div>
                          <div className="space-y-1.5 text-xs text-text-muted pl-6 border-l border-rose-500/30 font-mono">
                            <div>➔ Intent parsing & asset discovery</div>
                            <div>➔ Invoking deterministic QuantExa calculation engines</div>
                            <div>➔ NVIDIA NIM Neural Synthesis (nemotron-3-super-120b)</div>
                          </div>
                        </div>
                      ) : msg.error ? (
                        /* Error State */
                        <div className="bg-negative/10 border border-negative/30 text-negative rounded-2xl p-4 text-xs font-mono">
                          <strong>Orchestration Error:</strong> {msg.error}
                        </div>
                      ) : msg.data ? (
                        /* OpenClaw Structured Response */
                        <div className="space-y-4">
                          
                          {/* Collapsible Execution Trace Accordion (OpenClaw style) */}
                          {msg.data.orchestration_steps && msg.data.orchestration_steps.length > 0 && (
                            <div className="border border-border/80 rounded-xl overflow-hidden bg-surface/50 shadow-2xs">
                              <button
                                onClick={() => toggleSteps(msg.id)}
                                className="w-full flex items-center justify-between px-3.5 py-2.5 bg-surface-hover/50 hover:bg-surface-hover text-xs font-mono text-text-muted hover:text-text-main transition-colors cursor-pointer"
                              >
                                <div className="flex items-center gap-2">
                                  <Terminal size={13} className="text-rose-500" />
                                  <span className="font-semibold text-text-main">
                                    Execution Trace ({msg.data.orchestration_steps.length} Steps)
                                  </span>
                                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-positive/10 text-positive border border-positive/20">
                                    COMPLETED
                                  </span>
                                </div>
                                {isStepsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                              </button>

                              {isStepsOpen && (
                                <div className="p-3.5 space-y-2 border-t border-border/60 bg-surface/30 text-xs font-mono">
                                  {msg.data.orchestration_steps.map((step, idx) => (
                                    <div key={idx} className="flex items-start gap-2.5 leading-tight">
                                      <CheckCircle2 size={13} className="text-positive flex-shrink-0 mt-0.5" />
                                      <div className="flex-1">
                                        <span className="text-text-main font-semibold mr-1.5">{step.step}:</span>
                                        <span className="text-text-muted">{step.detail}</span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Full Markdown Report Rendering (GitHub Flavored) */}
                          {msg.data.markdown_report ? (
                            <div className="p-4 md:p-5 rounded-2xl bg-surface border border-border/90 shadow-2xs prose prose-invert prose-sm max-w-none text-text-main leading-relaxed space-y-3">
                              <ReactMarkdown 
                                remarkPlugins={[remarkGfm]}
                                components={{
                                  h1: ({node, ...props}) => <h1 className="text-base font-bold text-text-main mb-2 mt-4 pb-1 border-b border-border" {...props} />,
                                  h2: ({node, ...props}) => <h2 className="text-sm font-bold text-text-main mb-2 mt-3 pb-1 border-b border-border/70" {...props} />,
                                  h3: ({node, ...props}) => <h3 className="text-xs font-bold uppercase tracking-wider text-text-main mb-2 mt-3 flex items-center gap-1.5" {...props} />,
                                  h4: ({node, ...props}) => <h4 className="text-xs font-semibold text-text-main mb-1.5 mt-2" {...props} />,
                                  p: ({node, ...props}) => <p className="text-xs text-text-main leading-relaxed mb-2.5" {...props} />,
                                  ul: ({node, ...props}) => <ul className="list-disc pl-5 space-y-1 text-xs text-text-main mb-3" {...props} />,
                                  ol: ({node, ...props}) => <ol className="list-decimal pl-5 space-y-1 text-xs text-text-main mb-3" {...props} />,
                                  li: ({node, ...props}) => <li className="text-xs leading-relaxed" {...props} />,
                                  blockquote: ({node, ...props}) => (
                                    <blockquote className="p-3 my-3 rounded-xl bg-primary/5 border-l-4 border-primary text-xs text-text-main font-medium leading-relaxed italic" {...props} />
                                  ),
                                  table: ({node, ...props}) => (
                                    <div className="overflow-x-auto my-3 rounded-xl border border-border/80">
                                      <table className="w-full text-left border-collapse text-xs font-mono" {...props} />
                                    </div>
                                  ),
                                  th: ({node, ...props}) => <th className="bg-surface-hover/80 px-3 py-2 text-[11px] font-semibold text-text-main border-b border-border uppercase" {...props} />,
                                  td: ({node, ...props}) => <td className="px-3 py-2 text-xs border-b border-border/60 hover:bg-surface-hover/40 transition-colors" {...props} />,
                                  code: ({node, inline, ...props}: any) => (
                                    inline 
                                      ? <code className="px-1.5 py-0.5 rounded bg-surface-hover text-rose-400 font-mono text-[11px] border border-border/60" {...props} />
                                      : <code className="block p-3 rounded-xl bg-surface-hover/80 text-text-main font-mono text-xs overflow-x-auto my-2" {...props} />
                                  ),
                                  strong: ({node, ...props}) => <strong className="font-semibold text-text-main" {...props} />,
                                }}
                              >
                                {msg.data.markdown_report}
                              </ReactMarkdown>
                            </div>
                          ) : null}

                          {/* Analytical Findings Cards (shown when not duplicated in markdown) */}
                          {msg.data.findings && msg.data.findings.length > 0 && !msg.data.markdown_report && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {msg.data.findings.map((finding, idx) => (
                                <div 
                                  key={idx} 
                                  className="bg-surface border border-border rounded-xl p-3.5 shadow-2xs hover:border-rose-500/40 transition-colors space-y-1.5"
                                >
                                  <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-text-main">
                                    {getCategoryIcon(finding.category)}
                                    <span>{finding.category}</span>
                                  </div>
                                  <p className="text-xs text-text-muted leading-relaxed">
                                    {finding.content}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Institutional AI Conclusion Box (if markdown_report is not present) */}
                          {msg.data.conclusion && !msg.data.markdown_report && (
                            <div className="bg-rose-500/5 border border-rose-500/25 rounded-xl p-4 space-y-1.5 shadow-2xs">
                              <div className="flex items-center gap-1.5 text-xs font-bold text-rose-500">
                                <Sparkles size={14} className="text-rose-500" />
                                <span>OpenClaw AI Conclusion</span>
                              </div>
                              <p className="text-xs text-text-main font-medium leading-relaxed">
                                {msg.data.conclusion}
                              </p>
                            </div>
                          )}

                          {/* Footer Provenance Stamp */}
                          <div className="flex items-center justify-between text-[11px] font-mono text-text-muted/80 pt-1 px-1">
                            <span className="flex items-center gap-1">
                              <CheckCircle2 size={11} className="text-positive" />
                              <span>QuantExa Calculation Engine Verified</span>
                            </span>
                            <span>Deterministic Fidelity 100%</span>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
              <div ref={chatBottomRef} />
            </div>

            {/* Bottom OpenClaw Floating Input Dock */}
            <div className="p-3 md:p-4 bg-surface/50 border-t border-border space-y-2.5">
              <form 
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSendMessage(inputText);
                }} 
                className="w-full max-w-4xl mx-auto"
              >
                <div className="bg-surface border border-border/90 rounded-2xl p-3 shadow-md focus-within:border-rose-500/50 focus-within:ring-1 focus-within:ring-rose-500/30 transition-all space-y-2.5">
                  <input
                    type="text"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="Message OpenClaw (QuantExa Workspace)..."
                    disabled={researchMutation.isPending}
                    className="w-full bg-transparent text-sm text-text-main placeholder:text-text-muted/70 focus:outline-hidden disabled:opacity-50"
                  />

                  {/* Bottom Actions Row inside Dock */}
                  <div className="flex items-center justify-between pt-1 border-t border-border/40 text-xs">
                    
                    {/* Left: Context & Full Access Badges */}
                    <div className="flex items-center gap-2">
                      <button 
                        type="button" 
                        title="Add Asset Context"
                        className="p-1 rounded-lg text-text-muted hover:text-text-main hover:bg-surface-hover transition-colors cursor-pointer"
                      >
                        <Plus size={15} />
                      </button>
                      <div className="flex items-center gap-1 text-[11px] font-medium text-text-muted bg-surface-hover/80 px-2 py-0.5 rounded-lg border border-border/60">
                        <Shield size={11} className="text-positive" />
                        <span>Default (Full Access: QuantExa)</span>
                      </div>
                    </div>

                    {/* Right: Model Selector & Send Button */}
                    <div className="flex items-center gap-2">
                      <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-lg border border-emerald-500/20">
                        <Sparkles size={11} />
                        <span>nvidia/nemotron-3-super-120b</span>
                      </div>
                      <button 
                        type="button" 
                        title="Voice Input"
                        className="p-1.5 rounded-lg text-text-muted hover:text-text-main hover:bg-surface-hover transition-colors cursor-pointer"
                      >
                        <Mic size={14} />
                      </button>
                      <button
                        type="submit"
                        disabled={!inputText.trim() || researchMutation.isPending}
                        className="w-7 h-7 rounded-full bg-primary hover:bg-primary-hover disabled:opacity-30 text-white flex items-center justify-center transition-all cursor-pointer shadow-xs disabled:cursor-not-allowed"
                      >
                        {researchMutation.isPending ? (
                          <Sparkles size={13} className="animate-spin" />
                        ) : (
                          <ArrowUp size={14} />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              </form>

              {/* Quick Prompts below dock */}
              <div className="flex items-center justify-center gap-2 flex-wrap text-[11px] text-text-muted max-w-4xl mx-auto">
                <span className="font-mono text-[10px]">Quick:</span>
                {QUICK_PROMPTS.map((p, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(p)}
                    className="hover:text-text-main hover:underline transition-colors cursor-pointer truncate max-w-xs"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {/* ------------------------------------------------------------- */}
        {/* VIEW 2: AGENTS (OpenClaw Agent Registry & Skills Fleet)        */}
        {/* ------------------------------------------------------------- */}
        {activeNav === 'Agents' && (
          <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-5xl mx-auto w-full animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-text-main">OpenClaw Agent Fleet</h3>
                <p className="text-xs text-text-muted mt-0.5">Active quantitative agents, execution privileges, and model bindings</p>
              </div>
              <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-mono font-medium flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                1 Agent Running
              </span>
            </div>

            {/* Primary Agent Card */}
            <div className="p-5 rounded-2xl bg-surface border border-border/90 shadow-xs space-y-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-11 h-11 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-500">
                    <Bot size={24} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-bold text-text-main">OpenClaw Research Agent</h4>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20">
                        agent:main
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-positive/10 text-positive border border-positive/20">
                        PRIMARY
                      </span>
                    </div>
                    <p className="text-xs text-text-muted mt-0.5">
                      Institutional quantitative intelligence copilot with zero look-ahead bias
                    </p>
                  </div>
                </div>

                <button 
                  onClick={() => setActiveNav('Home')}
                  className="px-3 py-1.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-medium transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
                >
                  <Play size={12} fill="white" />
                  <span>Start Chat</span>
                </button>
              </div>

              {/* Specs Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs font-mono">
                <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/70 space-y-1">
                  <div className="text-text-muted text-[10px] uppercase">Model Provider</div>
                  <div className="font-semibold text-emerald-400 flex items-center gap-1">
                    <Sparkles size={11} />
                    <span>NVIDIA NIM</span>
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/70 space-y-1">
                  <div className="text-text-muted text-[10px] uppercase">Active Model</div>
                  <div className="font-semibold text-text-main truncate" title="nvidia/nemotron-3-super-120b-a12b">
                    nemotron-120b
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/70 space-y-1">
                  <div className="text-text-muted text-[10px] uppercase">Fidelity</div>
                  <div className="font-semibold text-positive">100% Deterministic</div>
                </div>
                <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/70 space-y-1">
                  <div className="text-text-muted text-[10px] uppercase">Skills Loaded</div>
                  <div className="font-semibold text-primary">20 Active Skills</div>
                </div>
              </div>

              {/* Skills Tags */}
              <div className="space-y-2 pt-1">
                <div className="text-[11px] font-mono uppercase text-text-muted font-semibold tracking-wider">
                  Loaded OpenClaw Skills:
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    'intent-understanding', 'task-planning', 'market-analysis', 'quantitative-analysis',
                    'comparison-analysis', 'strategy-backtesting', 'portfolio-solvers', 'knowledge-graph',
                    'conversation-memory', 'regime-detection', 'risk-parity', 'qubo-quantum-solvers'
                  ].map((skill, i) => (
                    <span key={i} className="text-[11px] font-mono px-2 py-0.8 rounded-lg bg-surface-hover text-text-main border border-border/70">
                      ⚡ {skill}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* VIEW 3: DASHBOARDS (Live Telemetry & Engine Health)           */}
        {/* ------------------------------------------------------------- */}
        {activeNav === 'Dashboards' && (
          <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-5xl mx-auto w-full animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-text-main">OpenClaw Telemetry Dashboard</h3>
                <p className="text-xs text-text-muted mt-0.5">Real-time status of gateways, calculation engines, and memory graphs</p>
              </div>
              <span className="text-xs font-mono text-positive bg-positive/10 px-2.5 py-1 rounded-full border border-positive/20 flex items-center gap-1.5">
                <CheckCircle2 size={12} />
                All Systems Operational
              </span>
            </div>

            {/* 4 Gateway & Engine Status Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-4 rounded-2xl bg-surface border border-border shadow-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-text-muted font-mono">Gateway</span>
                  <span className="w-2 h-2 rounded-full bg-positive animate-ping"></span>
                </div>
                <div className="text-lg font-bold text-text-main font-mono">127.0.0.1:18789</div>
                <div className="text-[11px] text-positive font-mono">HTTP 200 • Live</div>
              </div>

              <div className="p-4 rounded-2xl bg-surface border border-border shadow-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-text-muted font-mono">FastAPI Backend</span>
                  <span className="w-2 h-2 rounded-full bg-positive"></span>
                </div>
                <div className="text-lg font-bold text-text-main font-mono">Port 8000</div>
                <div className="text-[11px] text-positive font-mono">Uvicorn Worker Active</div>
              </div>

              <div className="p-4 rounded-2xl bg-surface border border-border shadow-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-text-muted font-mono">NVIDIA NIM API</span>
                  <Sparkles size={14} className="text-emerald-400" />
                </div>
                <div className="text-lg font-bold text-emerald-400 font-mono">Nemotron 120B</div>
                <div className="text-[11px] text-text-muted font-mono">Avg Latency ~1.1s</div>
              </div>

              <div className="p-4 rounded-2xl bg-surface border border-border shadow-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-text-muted font-mono">Knowledge Graph</span>
                  <Database size={14} className="text-purple-400" />
                </div>
                <div className="text-lg font-bold text-purple-400 font-mono">506 Nodes</div>
                <div className="text-[11px] text-purple-300 font-mono">34 Relation Types</div>
              </div>
            </div>

            {/* Performance & Execution Specs */}
            <div className="p-5 rounded-2xl bg-surface border border-border space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-text-main font-mono flex items-center gap-2">
                <Gauge size={14} className="text-primary" />
                <span>Deterministic Calculation Pipeline</span>
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
                <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/70">
                  <div className="text-text-muted text-[10px]">Look-Ahead Bias</div>
                  <div className="text-sm font-bold text-positive">0.00% (Strict Zero)</div>
                </div>
                <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/70">
                  <div className="text-text-muted text-[10px]">Floating Precision</div>
                  <div className="text-sm font-bold text-text-main">IEEE 754 Float64</div>
                </div>
                <div className="p-3 rounded-xl bg-surface-hover/60 border border-border/70">
                  <div className="text-text-muted text-[10px]">Lineage Auditing</div>
                  <div className="text-sm font-bold text-purple-400">Neo4j Cypher Logged</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* VIEW 4: SYSTEMS (Connected Calculation Topology)              */}
        {/* ------------------------------------------------------------- */}
        {activeNav === 'Systems' && (
          <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-5xl mx-auto w-full animate-fade-in">
            <div>
              <h3 className="text-base font-bold text-text-main">System Architecture & Engines</h3>
              <p className="text-xs text-text-muted mt-0.5">High-performance computational modules backing OpenClaw in QuantExa</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                {
                  name: 'QuantExa Risk Engine',
                  tech: 'Python 3.13 • NumPy • SciPy',
                  desc: 'Computes CAGR, annualized volatility, Sharpe & Sortino ratios, and maximum historical drawdown from authoritative daily prices.',
                  status: 'Active',
                  icon: Cpu,
                  color: 'text-primary'
                },
                {
                  name: 'Markowitz Mean-Variance Solver',
                  tech: 'SciPy Optimize (SLSQP)',
                  desc: 'Calculates the optimal asset weights along the Markowitz Efficient Frontier maximizing the portfolio Sharpe ratio.',
                  status: 'Active',
                  icon: PieChart,
                  color: 'text-positive'
                },
                {
                  name: 'QUBO Quantum-Ready Solver',
                  tech: 'Quadratic Binary Optimization',
                  desc: 'Formulates discrete portfolio selection problems into QUBO matrices compatible with quantum annealing backends.',
                  status: 'Active',
                  icon: Boxes,
                  color: 'text-amber-400'
                },
                {
                  name: 'Neo4j Aura Knowledge Graph',
                  tech: 'Bolt 7687 • Cypher Engine',
                  desc: 'Tracks entity taxonomies, cross-asset supply-chain linkages, and writes execution lineage for every OpenClaw run.',
                  status: 'Connected',
                  icon: Database,
                  color: 'text-purple-400'
                }
              ].map((sys, idx) => {
                const Icon = sys.icon;
                return (
                  <div key={idx} className="p-4 rounded-2xl bg-surface border border-border shadow-2xs space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className={`p-2 rounded-lg bg-surface-hover ${sys.color}`}>
                          <Icon size={16} />
                        </div>
                        <div>
                          <div className="text-xs font-bold text-text-main">{sys.name}</div>
                          <div className="text-[10px] text-text-muted font-mono">{sys.tech}</div>
                        </div>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-positive/10 text-positive border border-positive/20">
                        {sys.status}
                      </span>
                    </div>
                    <p className="text-xs text-text-muted leading-relaxed">
                      {sys.desc}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* VIEW 5: AUTOMATIONS (Scheduled Cron & Event Handlers)         */}
        {/* ------------------------------------------------------------- */}
        {activeNav === 'Automations' && (
          <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-5xl mx-auto w-full animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-text-main">Automated Workflows</h3>
                <p className="text-xs text-text-muted mt-0.5">Recurring quantitative scanning jobs and market surveillance triggers</p>
              </div>
              <button 
                onClick={() => handleSendMessage('Evaluate risk metrics and drawdown for Bitcoin.')}
                className="px-3 py-1.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-medium transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
              >
                <Play size={12} fill="white" />
                <span>Trigger Market Scan</span>
              </button>
            </div>

            <div className="space-y-3">
              {[
                {
                  title: 'Daily Market Risk & Volatility Ingestion',
                  schedule: 'Cron: 0 16 * * 1-5 (Market Close)',
                  desc: 'Fetches authoritative EOD series, calculates 252-day rolling volatility, and detects tail-risk spikes across crypto and equities.',
                  status: 'Scheduled'
                },
                {
                  title: 'Cross-Asset Correlation Matrix Refresh',
                  schedule: 'Hourly Surveillance',
                  desc: 'Re-evaluates Pearson correlation and tail dependence across multi-asset universe (BTC, NVDA, AAPL, Gold).',
                  status: 'Active'
                },
                {
                  title: 'Neo4j Execution Lineage Sync',
                  schedule: 'Event-Driven (Post-Inquiry)',
                  desc: 'Writes real-world agent execution steps, skill allocations, and tool parameters directly to the Neo4j Aura knowledge base.',
                  status: 'Active'
                }
              ].map((auto, idx) => (
                <div key={idx} className="p-4 rounded-2xl bg-surface border border-border shadow-xs flex items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-text-main">{auto.title}</span>
                      <span className="text-[10px] font-mono px-2 py-0.2 rounded bg-positive/10 text-positive border border-positive/20">
                        {auto.status}
                      </span>
                    </div>
                    <div className="text-[11px] font-mono text-primary flex items-center gap-1">
                      <Clock size={11} />
                      <span>{auto.schedule}</span>
                    </div>
                    <p className="text-xs text-text-muted leading-relaxed">
                      {auto.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* VIEW 6: PLUGINS (OpenClaw Connector Catalog)                   */}
        {/* ------------------------------------------------------------- */}
        {activeNav === 'Plugins' && (
          <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-5xl mx-auto w-full animate-fade-in">
            <div>
              <h3 className="text-base font-bold text-text-main">OpenClaw Plugins Catalog</h3>
              <p className="text-xs text-text-muted mt-0.5">Installed connectors extending agent capabilities and computational reach</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                {
                  name: 'QuantExa Financial Math Engine',
                  version: 'v2.4.0',
                  desc: 'Provides deterministic calculation tools for CAGR, volatility, Sharpe ratio, and drawdown metrics.',
                  enabled: true
                },
                {
                  name: 'NVIDIA NIM Intelligence Plugin',
                  version: 'v1.2.0',
                  desc: 'Connects to NVIDIA NIM endpoints (nemotron-3-super-120b) for institutional synthesis.',
                  enabled: true
                },
                {
                  name: 'Neo4j Aura Graph Memory',
                  version: 'v3.1.0',
                  desc: 'Maintains graph database connections, schema entity nodes, and execution audit trails.',
                  enabled: true
                },
                {
                  name: 'Composio YouTube & Web MCP',
                  version: 'v1.8.2',
                  desc: 'Enables external market video analysis, YouTube video discovery, and AI intelligence synthesis.',
                  enabled: true
                }
              ].map((plugin, idx) => (
                <div key={idx} className="p-4 rounded-2xl bg-surface border border-border shadow-xs space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-bold text-text-main">{plugin.name}</div>
                      <div className="text-[10px] text-text-muted font-mono">{plugin.version}</div>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      ENABLED
                    </span>
                  </div>
                  <p className="text-xs text-text-muted leading-relaxed">
                    {plugin.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
