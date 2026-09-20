import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Overview } from './pages/Overview';
import { StrategyLab } from './pages/StrategyLab';
import { AssetExplorer } from './pages/AssetExplorer';
import { Correlation } from './pages/Correlation';
import { Methodology } from './pages/Methodology';

import { Portfolio } from './pages/Portfolio';
import { KnowledgeGraph } from './pages/KnowledgeGraph';
import { AiResearch } from './pages/AiResearch';
import { MarketAnalysis } from './pages/MarketAnalysis';
import { Reports } from './pages/Reports';
import { DataPipeline } from './pages/DataPipeline';

import { ThemeProvider } from './contexts/ThemeContext';
import { BatchProvider } from './contexts/BatchContext';

function App() {
  return (
    <ThemeProvider>
      <BatchProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Overview />} />
              <Route path="pipeline" element={<DataPipeline />} />
              <Route path="market-analysis" element={<MarketAnalysis />} />
              <Route path="explorer" element={<AssetExplorer />} />
              <Route path="correlation" element={<Correlation />} />
              <Route path="lab" element={<StrategyLab />} />
              <Route path="portfolio" element={<Portfolio />} />
              <Route path="graph" element={<KnowledgeGraph />} />
              <Route path="ai-research" element={<AiResearch />} />
              <Route path="reports" element={<Reports />} />
              <Route path="methodology" element={<Methodology />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </BatchProvider>
    </ThemeProvider>
  );
}

export default App;
