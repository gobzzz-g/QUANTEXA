import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Overview } from './pages/Overview';
import { StrategyLab } from './pages/StrategyLab';
import { AssetExplorer } from './pages/AssetExplorer';
import { Correlation } from './pages/Correlation';
import { Robustness } from './pages/Robustness';
import { Regimes } from './pages/Regimes';
import { Methodology } from './pages/Methodology';

import { Portfolio } from './pages/Portfolio';
import { KnowledgeGraph } from './pages/KnowledgeGraph';
import { AiResearch } from './pages/AiResearch';
import { MarketAnalysis } from './pages/MarketAnalysis';
import { Reports } from './pages/Reports';

import { ThemeProvider } from './contexts/ThemeContext';

function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="market-analysis" element={<MarketAnalysis />} />
          <Route path="explorer" element={<AssetExplorer />} />
          <Route path="correlation" element={<Correlation />} />
          <Route path="lab" element={<StrategyLab />} />
          <Route path="robustness" element={<Robustness />} />
          <Route path="regimes" element={<Regimes />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="graph" element={<KnowledgeGraph />} />
          <Route path="ai-research" element={<AiResearch />} />
          <Route path="reports" element={<Reports />} />
          <Route path="methodology" element={<Methodology />} />
        </Route>
      </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
