import React, { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';

interface ThemeContextType {
  theme: Theme;
  actualTheme: 'light' | 'dark'; // The resolved theme if 'system' is selected
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem('quantExa-theme');
    return (saved as Theme) || 'system';
  });
  
  const [actualTheme, setActualTheme] = useState<'light' | 'dark'>('dark');

  useEffect(() => {
    const root = window.document.documentElement;
    const isDarkSystem = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    const resolvedTheme = theme === 'system' ? (isDarkSystem ? 'dark' : 'light') : theme;
    
    setActualTheme(resolvedTheme);
    
    root.classList.remove('light', 'dark');
    root.classList.add(resolvedTheme);
    
    localStorage.setItem('quantExa-theme', theme);
  }, [theme]);

  // Listen for system theme changes if using system
  useEffect(() => {
    if (theme !== 'system') return;
    
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      const isDarkSystem = mediaQuery.matches;
      setActualTheme(isDarkSystem ? 'dark' : 'light');
      
      const root = window.document.documentElement;
      root.classList.remove('light', 'dark');
      root.classList.add(isDarkSystem ? 'dark' : 'light');
    };
    
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, actualTheme, setTheme: setThemeState }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
