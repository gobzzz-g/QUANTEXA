export function getChartTheme(actualTheme: 'light' | 'dark') {
  if (actualTheme === 'dark') {
    return {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: { color: '#F1F5F9' },
      xaxis: {
        gridcolor: 'rgba(59, 130, 246, 0.1)',
        zerolinecolor: 'rgba(59, 130, 246, 0.2)',
        tickfont: { color: '#94A3B8' }
      },
      yaxis: {
        gridcolor: 'rgba(59, 130, 246, 0.1)',
        zerolinecolor: 'rgba(59, 130, 246, 0.2)',
        tickfont: { color: '#94A3B8' }
      }
    };
  }

  // Light Mode
  return {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: '#0F172A' },
    xaxis: {
      gridcolor: 'rgba(100, 116, 139, 0.15)',
      zerolinecolor: 'rgba(100, 116, 139, 0.25)',
      tickfont: { color: '#64748B' }
    },
    yaxis: {
      gridcolor: 'rgba(100, 116, 139, 0.15)',
      zerolinecolor: 'rgba(100, 116, 139, 0.25)',
      tickfont: { color: '#64748B' }
    }
  };
}
