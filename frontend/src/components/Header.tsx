import { Search, Bell, Settings, UserCircle, Sun, Moon } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';

export function Header() {
  const location = useLocation();
  const { actualTheme, setTheme } = useTheme();
  
  const toggleTheme = () => {
    setTheme(actualTheme === 'dark' ? 'light' : 'dark');
  };
  
  const formatPathname = (path: string) => {
    if (path === '/') return 'Overview';
    return path
      .replace('/', '')
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  return (
    <header className="h-16 border-b border-border bg-surface/50 backdrop-blur-md sticky top-0 z-40 flex items-center justify-between px-6 transition-colors duration-200">
      {/* Breadcrumb / Title */}
      <div className="flex items-center">
        <h2 className="text-lg font-semibold text-text-main">{formatPathname(location.pathname)}</h2>
      </div>

      {/* Right Actions */}
      <div className="flex items-center space-x-4">
        {/* Search */}
        <div className="relative group cursor-pointer" onClick={() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))}>
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-4 w-4 text-text-muted group-hover:text-text-main transition-colors" />
          </div>
          <div className="bg-background border border-border rounded-md py-1.5 pl-9 pr-3 text-sm text-text-muted flex items-center w-64 group-hover:border-primary transition-colors">
            <span>Search assets, strategies...</span>
            <span className="ml-auto text-xs bg-surface border border-border rounded px-1.5 py-0.5">⌘K</span>
          </div>
        </div>

        {/* Icons */}
        <button className="text-text-muted hover:text-text-main transition-colors">
          <Bell className="w-5 h-5" />
        </button>
        <button onClick={toggleTheme} className="text-text-muted hover:text-text-main transition-colors" title="Toggle Theme">
          {actualTheme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>
        <button className="text-text-muted hover:text-text-main transition-colors">
          <Settings className="w-5 h-5" />
        </button>
        <div className="h-6 w-px bg-border mx-2"></div>
        <button className="text-text-muted hover:text-text-main transition-colors flex items-center">
          <UserCircle className="w-6 h-6 mr-2" />
          <span className="text-sm font-medium">Analyst</span>
        </button>
      </div>
    </header>
  );
}
