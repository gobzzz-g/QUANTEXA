import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  LineChart,
  BarChart2,
  Activity,
  FlaskConical,
  PieChart,
  Network,
  BrainCircuit,
  FileText,
  BookOpen,
  Database,
  Search,
  Bell,
  Settings,
  UserCircle,
  Sun,
  Moon,
} from 'lucide-react';
import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';

const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: LayoutDashboard },
  { path: '/pipeline', label: 'Data & Pipeline', icon: Database },
  { path: '/market-analysis', label: 'Market Analysis', icon: LineChart },
  { path: '/explorer', label: 'Asset Explorer', icon: BarChart2 },
  { path: '/correlation', label: 'Correlation & Risk', icon: Activity },
  { path: '/lab', label: 'Strategy Lab', icon: FlaskConical },
  { path: '/portfolio', label: 'Portfolio', icon: PieChart },
  { path: '/graph', label: 'Knowledge Graph', icon: Network },
  { path: '/ai-research', label: 'AI Research', icon: BrainCircuit },
  { path: '/reports', label: 'Reports', icon: FileText },
  { path: '/methodology', label: 'Methodology', icon: BookOpen },
];

export function Sidebar() {
  const [isLive] = useState(true);
  const { actualTheme, setTheme } = useTheme();
  const location = useLocation();

  const toggleTheme = () => setTheme(actualTheme === 'dark' ? 'light' : 'dark');

  const formatPathname = (path: string) => {
    if (path === '/') return 'Overview';
    return path
      .replace('/', '')
      .split('-')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-surface/80 backdrop-blur-xl shadow-sm">
      {/* ── Top Bar: Brand + Actions ── */}
      <div className="flex items-center justify-between px-6 h-14">
        {/* Brand */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Activity className="w-4.5 h-4.5 text-primary" />
          </div>
          <div className="leading-none">
            <span className="text-base font-bold tracking-tight text-text-main">QuantExa</span>
            <span className="hidden sm:block text-[9px] text-text-muted uppercase tracking-widest font-semibold mt-0.5">
              Financial Intelligence
            </span>
          </div>
        </div>

        {/* Page title (mobile breadcrumb) */}
        <span className="sm:hidden text-sm font-semibold text-text-main">
          {formatPathname(location.pathname)}
        </span>

        {/* Right actions */}
        <div className="flex items-center gap-1">
          {/* Search */}
          <div
            className="hidden md:flex items-center gap-2 bg-background border border-border rounded-lg px-3 py-1.5 cursor-pointer hover:border-primary transition-colors group mr-2"
            onClick={() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))}
          >
            <Search className="w-3.5 h-3.5 text-text-muted group-hover:text-primary transition-colors" />
            <span className="text-xs text-text-muted w-32">Search assets...</span>
            <span className="text-[10px] bg-surface border border-border rounded px-1 py-0.5 text-text-muted">⌘K</span>
          </div>

          {/* Live indicators */}
          <div className="hidden lg:flex items-center gap-3 mr-3 px-3 py-1 rounded-lg bg-background border border-border">
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-positive' : 'bg-negative'}`} />
              <span className="text-[10px] font-medium text-text-muted">API</span>
            </div>
            <div className="w-px h-3 bg-border" />
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-positive animate-pulse' : 'bg-negative'}`} />
              <span className="text-[10px] font-medium text-text-muted">Live</span>
            </div>
          </div>

          <button className="p-2 rounded-lg text-text-muted hover:text-text-main hover:bg-surface-hover transition-colors">
            <Bell className="w-4 h-4" />
          </button>
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg text-text-muted hover:text-text-main hover:bg-surface-hover transition-colors"
            title="Toggle theme"
          >
            {actualTheme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          <button className="p-2 rounded-lg text-text-muted hover:text-text-main hover:bg-surface-hover transition-colors">
            <Settings className="w-4 h-4" />
          </button>
          <div className="w-px h-5 bg-border mx-1" />
          <button className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-text-muted hover:bg-surface-hover transition-colors">
            <UserCircle className="w-5 h-5" />
            <span className="hidden sm:block text-xs font-medium">Analyst</span>
          </button>
        </div>
      </div>

      {/* ── Nav Tabs Row ── */}
      <div className="border-t border-border/60 overflow-x-auto no-scrollbar">
        <nav className="flex items-center px-4 gap-0.5 min-w-max">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium whitespace-nowrap border-b-2 transition-all duration-200 ${
                  isActive
                    ? 'border-primary text-primary'
                    : 'border-transparent text-text-muted hover:text-text-main hover:border-border'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon className={`w-3.5 h-3.5 ${isActive ? 'text-primary' : 'text-text-muted'}`} />
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
