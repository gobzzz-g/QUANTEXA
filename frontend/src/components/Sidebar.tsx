import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  LineChart, 
  BarChart2, 
  Activity, 
  FlaskConical, 
  ShieldAlert, 
  Layers, 
  PieChart, 
  Network, 
  BrainCircuit, 
  FileText, 
  BookOpen
} from 'lucide-react';
import { useState } from 'react';

const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: LayoutDashboard },
  { path: '/market-analysis', label: 'Market Analysis', icon: LineChart },
  { path: '/explorer', label: 'Asset Explorer', icon: BarChart2 },
  { path: '/correlation', label: 'Correlation & Risk', icon: Activity },
  { path: '/lab', label: 'Strategy Lab', icon: FlaskConical },
  { path: '/robustness', label: 'Robustness', icon: ShieldAlert },
  { path: '/regimes', label: 'Market Regimes', icon: Layers },
  { path: '/portfolio', label: 'Portfolio', icon: PieChart },
  { path: '/graph', label: 'Knowledge Graph', icon: Network },
  { path: '/ai-research', label: 'AI Research', icon: BrainCircuit },
  { path: '/reports', label: 'Reports', icon: FileText },
  { path: '/methodology', label: 'Methodology', icon: BookOpen },
];

export function Sidebar() {
  const [isLive] = useState(true);

  return (
    <aside className="w-64 border-r border-border bg-surface flex flex-col h-screen sticky top-0">
      {/* Brand */}
      <div className="h-16 flex items-center px-6 border-b border-border shrink-0">
        <Activity className="w-6 h-6 text-primary mr-2" />
        <div>
          <h1 className="text-lg font-bold tracking-tight text-text-main leading-none">QuantExa</h1>
          <p className="text-[10px] text-text-muted uppercase tracking-wider font-semibold mt-1">Financial Intelligence</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1 custom-scrollbar">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex items-center px-3 py-2 text-sm font-medium rounded-md transition-all duration-200 group relative ${
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-text-muted hover:bg-surface-hover hover:text-text-main'
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-primary rounded-r-full" />
                )}
                <item.icon className={`w-4 h-4 mr-3 ${isActive ? 'text-primary' : 'text-text-muted group-hover:text-text-main'}`} />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Status Footer */}
      <div className="p-4 border-t border-border shrink-0 bg-surface-hover/30">
        <div className="flex flex-col space-y-2">
          <div className="flex items-center text-xs font-medium text-text-muted">
            <span className={`w-2 h-2 rounded-full mr-2 ${isLive ? 'bg-positive' : 'bg-negative'}`}></span>
            API Connected
          </div>
          <div className="flex items-center text-xs font-medium text-text-muted">
            <span className={`w-2 h-2 rounded-full mr-2 ${isLive ? 'bg-positive animate-pulse' : 'bg-negative'}`}></span>
            Market Data Live
          </div>
        </div>
      </div>
    </aside>
  );
}
