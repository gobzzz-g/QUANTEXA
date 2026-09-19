import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { GraphResponse, GraphContextResponse } from '../api/types';
import ForceGraph2D from 'react-force-graph-2d';
import { Search, ZoomIn, ZoomOut, Maximize, Filter, Sidebar, Database, Activity, Map, ArrowRight, Layers, Network } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

export function KnowledgeGraph() {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [layout, setLayout] = useState<'Force Graph' | 'Sequential Layout' | 'Radial Layout'>('Force Graph');
  const [showExplorer, setShowExplorer] = useState(true);
  const { actualTheme } = useTheme();
  
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  
  const { data: graphData, isLoading: graphLoading } = useQuery<GraphResponse>({
    queryKey: ['graph'],
    queryFn: async () => (await apiClient.get('/graph')).data
  });
  
  const { data: contextData, isLoading: contextLoading } = useQuery<GraphContextResponse>({
    queryKey: ['graph_context', selectedNodeId],
    queryFn: async () => (await apiClient.get(`/graph/${selectedNodeId}`)).data,
    enabled: !!selectedNodeId
  });

  // Track container dimensions for ForceGraph
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
      }
    };
    
    // Set initial size
    updateDimensions();

    if (!containerRef.current) return;
    
    // Listen for resizes
    const observer = new ResizeObserver(() => {
      // Use requestAnimationFrame to avoid "ResizeObserver loop completed with undelivered notifications"
      window.requestAnimationFrame(updateDimensions);
    });
    
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [showExplorer]); // Re-run if explorer toggles, as it changes the layout

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNodeId(node.id);
    if (graphRef.current) {
      graphRef.current.centerAt(node.x, node.y, 1000);
      graphRef.current.zoom(1.5, 1000);
    }
  }, []);

  const processedGraphData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] };
    
    // Deep clone to avoid mutating react-query cache
    const nodes = JSON.parse(JSON.stringify(graphData.nodes));
    const links = JSON.parse(JSON.stringify(graphData.links));
    
    // Group nodes by type for layouts
    const groups: Record<string, any[]> = {};
    nodes.forEach((n: any) => {
      if (!groups[n.type]) groups[n.type] = [];
      groups[n.type].push(n);
    });
    
    const typeOrder = ['Asset', 'Portfolio', 'Strategy', 'Market Regime', 'Backtest', 'Robustness', 'QUBO'];
    const activeTypes = typeOrder.filter(t => groups[t]);
    
    // Apply layout positions
    if (layout === 'Force Graph') {
      nodes.forEach((n: any) => {
        delete n.fx;
        delete n.fy;
      });
    } else if (layout === 'Sequential Layout') {
      activeTypes.forEach((t, i) => {
        const yBase = (i - activeTypes.length / 2) * 100; // REDUCED vertical spacing between tiers
        const groupNodes = groups[t];
        
        // Arrange horizontally, wrapping into rows if there are many nodes (GitNexus style)
        const columns = Math.min(groupNodes.length, Math.ceil(Math.sqrt(groupNodes.length) * 2));
        
        groupNodes.forEach((n, j) => {
          const col = j % columns;
          const row = Math.floor(j / columns);
          
          const x = (col - columns / 2) * 20; // REDUCED horizontal spacing
          const yOffset = row * 20; // REDUCED vertical spacing between rows
          
          n.fx = x;
          n.fy = yBase + yOffset;
        });
      });
    } else if (layout === 'Radial Layout') {
      activeTypes.forEach((t, i) => {
        // REDUCED spacing between rings
        const baseRadius = i === 0 ? (groups[t].length === 1 ? 0 : 40) : 120 + i * 150;
        const groupNodes = groups[t];
        
        if (i === 0 && groupNodes.length === 1) {
          groupNodes[0].fx = 0;
          groupNodes[0].fy = 0;
          return;
        }
        
        // Band width capped at 120px to keep rings tighter
        const bandWidth = Math.min(120, Math.ceil(groupNodes.length / 5) * 10);
        
        const subRings = Math.max(1, Math.floor(bandWidth / 10));
        
        groupNodes.forEach((n, j) => {
          const ringOffset = subRings > 1 ? (j % subRings) * (bandWidth / subRings) : 0;
          const r = baseRadius + ringOffset;
          
          const angle = (Math.floor(j / subRings) / Math.ceil(groupNodes.length / subRings)) * 2 * Math.PI + (ringOffset * 0.05);
          
          n.fx = Math.cos(angle) * r;
          n.fy = Math.sin(angle) * r;
        });
      });
    }
    
    // Filter by search
    if (searchQuery) {
        const q = searchQuery.toLowerCase();
        nodes.forEach((n: any) => {
            const matches = n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q);
            n._highlight = matches;
        });
    }
    
    return { nodes, links };
  }, [graphData, layout, searchQuery]);

  // Reheat simulation when layout changes and adjust physics
  useEffect(() => {
    if (graphRef.current) {
        // Bring nodes much closer together
        graphRef.current.d3Force('charge').strength(-80);
        graphRef.current.d3Force('link').distance(40);

        if (layout === 'Force Graph') {
            graphRef.current.d3ReheatSimulation();
        } else {
            // For fixed layouts, run a quick simulation to settle links then stop
            graphRef.current.d3ReheatSimulation();
            setTimeout(() => {
                if (graphRef.current) graphRef.current.d3Force('charge').strength(0);
            }, 100);
        }
    }
  }, [layout, processedGraphData]);

  // Calculate node degrees and connection map for sizing and hover effects
  const { nodeDegrees, nodeConnections } = useMemo(() => {
    if (!graphData) return { nodeDegrees: {}, nodeConnections: {} };
    const degrees: Record<string, number> = {};
    const connections: Record<string, Set<string>> = {};
    
    graphData.nodes.forEach(n => {
      degrees[n.id] = 0;
      connections[n.id] = new Set();
    });
    
    graphData.links.forEach((l: any) => {
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      if (degrees[src] !== undefined) {
        degrees[src]++;
        connections[src].add(tgt);
      }
      if (degrees[tgt] !== undefined) {
        degrees[tgt]++;
        connections[tgt].add(src);
      }
    });
    return { nodeDegrees: degrees, nodeConnections: connections };
  }, [graphData]);

  const [hoverNode, setHoverNode] = useState<string | null>(null);

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const isSelected = selectedNodeId === node.id;
    const isHovered = hoverNode === node.id;
    const isSearched = node._highlight;
    
    let isConnected = false;
    if (selectedNodeId && nodeConnections[selectedNodeId]?.has(node.id)) isConnected = true;
    if (hoverNode && nodeConnections[hoverNode]?.has(node.id)) isConnected = true;
    
    const hasFocus = selectedNodeId || hoverNode;
    const isFaded = hasFocus && !isSelected && !isHovered && !isConnected && !isSearched;

    const degree = nodeDegrees[node.id] || 0;
    
    // Explicit sizing requested by user (BTC, GOLD, NVDA large, else medium/small)
    const isMajorAsset = node.type === 'Asset' && ['BTC', 'GOLD', 'NVDA'].includes(node.name?.toUpperCase());
    
    let baseRadius = 3;
    if (isMajorAsset) baseRadius = 8;
    else if (node.type === 'Asset') baseRadius = 5;
    else if (['Strategy', 'Backtest', 'Portfolio', 'Market Regime'].includes(node.type)) baseRadius = 4;
    
    const radius = baseRadius + Math.min(degree * 0.3, 4); 
    
    let color = '#6B7280'; // Muted blue/gray
    if (node.type === 'Asset') color = '#2563EB'; // QuantExa blue
    else if (node.type === 'Strategy') color = '#8B5CF6'; // Violet
    else if (node.type === 'Backtest') color = '#06B6D4'; // Cyan/blue
    else if (node.type === 'Market Regime') color = '#F59E0B'; // Amber
    else if (node.type === 'Portfolio') color = '#10B981'; // Green
    else if (node.type === 'QUBO') color = '#D946EF'; // Magenta
    
    // Dim if not in focus
    if (isFaded) {
      ctx.globalAlpha = 0.15;
    } else {
      ctx.globalAlpha = 1;
    }
    
    // Ambient glow for important nodes
    if ((isMajorAsset || degree > 8 || isSelected || isHovered) && !isFaded) {
        ctx.shadowBlur = isSelected ? 20 : 15;
        ctx.shadowColor = color;
    } else {
        ctx.shadowBlur = 0;
    }

    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.shadowBlur = 0; // reset
    
    // Halos
    if (isSelected || isHovered || isSearched) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius + (isSelected ? 4 : 2), 0, 2 * Math.PI, false);
      ctx.lineWidth = (isSelected ? 2 : 1) / globalScale;
      ctx.strokeStyle = color;
      ctx.stroke();
    }
    
    const isImportant = degree > 5 || node.type === 'Asset';
    const showLabel = globalScale > 1.8 || isSelected || isHovered || isSearched || isConnected || (isImportant && globalScale > 0.6) || (isMajorAsset && globalScale > 0.3);
    
    if (showLabel && !isFaded) {
        const label = node.name;
        const fontSize = (isSelected || isHovered ? 12 : 10) / globalScale;
        ctx.font = `${fontSize}px Inter, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        
        // Add a small dark background pill for the text to improve readability against grid/edges
        const textWidth = ctx.measureText(label).width;
        ctx.fillStyle = actualTheme === 'dark' ? 'rgba(7, 17, 31, 0.7)' : 'rgba(255, 255, 255, 0.85)';
        ctx.fillRect(node.x - textWidth/2 - 2/globalScale, node.y + radius + 2/globalScale, textWidth + 4/globalScale, fontSize + 4/globalScale);
        
        ctx.fillStyle = isSelected || isHovered ? (actualTheme === 'dark' ? '#FFFFFF' : '#0F172A') : (actualTheme === 'dark' ? '#D1D5DB' : '#475569');
        ctx.fillText(label, node.x, node.y + radius + (8/globalScale) + (fontSize/2));
    }
    
    ctx.globalAlpha = 1;
  }, [selectedNodeId, hoverNode, nodeDegrees, nodeConnections, actualTheme]);

  // Explorer categories
  const explorerGroups = useMemo(() => {
    if (!graphData) return {};
    const groups: Record<string, any[]> = {};
    graphData.nodes.forEach(n => {
      if (!groups[n.type]) groups[n.type] = [];
      groups[n.type].push(n);
    });
    return groups;
  }, [graphData]);

  if (graphLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center">
          <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin mb-4"></div>
          <p className="text-text-muted">Constructing Knowledge Graph from Supabase...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-10rem)] min-h-[600px] bg-background text-text-main font-sans rounded-xl border border-border overflow-hidden relative shadow-lg">
      {/* Top Bar */}
      <div className="h-14 border-b border-border flex items-center justify-between px-4 bg-surface shrink-0">
        <div className="flex items-center space-x-4">
          <button 
            onClick={() => setShowExplorer(!showExplorer)}
            className={`p-1.5 rounded flex items-center gap-2 text-sm font-medium transition-colors ${showExplorer ? 'bg-surface-highlight text-text-main' : 'hover:bg-surface-hover text-text-muted'}`}
          >
            <Sidebar size={16} />
            EXPLORER
          </button>
          
          <div className="relative w-64">
            <Search className="absolute left-3 top-2 text-text-muted w-4 h-4" />
            <input 
              type="text" 
              placeholder="Search by meaning or name..." 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-surface border border-border rounded px-9 py-1.5 text-sm text-text-main placeholder-text-muted focus:outline-none focus:border-primary"
            />
          </div>
          
          <button className="flex items-center gap-2 text-sm text-text-muted hover:text-text-main px-3 py-1.5 rounded hover:bg-surface-hover">
            <Filter size={16} />
            FILTERS
          </button>
        </div>
        
        <div className="flex items-center space-x-1 bg-surface-highlight p-1 rounded-md border border-border">
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted px-3">Layout</span>
          {(['Force Graph', 'Sequential Layout', 'Radial Layout'] as const).map(l => (
            <button
              key={l}
              onClick={() => setLayout(l)}
              className={`px-3 py-1 text-xs font-medium rounded ${layout === l ? 'bg-surface text-text-main shadow border border-border' : 'text-text-muted hover:text-text-main hover:bg-surface-hover'}`}
            >
              {l === 'Force Graph' && <Activity size={12} className="inline mr-1.5 mb-0.5" />}
              {l === 'Sequential Layout' && <Layers size={12} className="inline mr-1.5 mb-0.5" />}
              {l === 'Radial Layout' && <Map size={12} className="inline mr-1.5 mb-0.5" />}
              {l.toUpperCase()}
            </button>
          ))}
        </div>
        
        <div className="flex flex-col text-right">
          <div className="text-xs text-primary font-mono">{graphData?.nodes.length} nodes • {graphData?.links.length} edges</div>
          <div className="text-[10px] text-text-muted flex items-center justify-end gap-1">
            <Database size={10} /> SUPABASE HISTORICAL DATA
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden relative">
        
        {/* Left Explorer */}
        {showExplorer && (
          <div className="w-64 border-r border-border bg-surface shrink-0 overflow-y-auto custom-scrollbar flex flex-col">
            <div className="p-4 border-b border-border">
              <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Knowledge Explorer</h2>
            </div>
            
            <div className="p-2 space-y-4">
              {['Company', 'Asset', 'AssetClass', 'Sector', 'Industry', 'Strategy', 'Metric'].map(type => {
                const nodes = explorerGroups[type];
                if (!nodes || nodes.length === 0) return null;
                
                return (
                  <div key={type} className="px-2">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-text-muted mb-2 flex justify-between">
                      {type} <span className="text-text-muted">{nodes.length}</span>
                    </div>
                    <ul className="space-y-0.5">
                      {nodes.sort((a,b) => a.name.localeCompare(b.name)).map(n => (
                        <li key={n.id}>
                          <button 
                            onClick={() => handleNodeClick(n)}
                            className={`w-full text-left px-2 py-1.5 text-xs rounded flex items-center gap-2 truncate ${selectedNodeId === n.id ? 'bg-primary/10 text-primary font-medium' : 'text-text-main hover:bg-surface-hover'}`}
                          >
                            <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                n.type === 'Asset' || n.type === 'Company' ? 'bg-[#10B981]' : 
                                n.type === 'Sector' || n.type === 'Industry' ? 'bg-[#8B5CF6]' : 
                                n.type === 'Strategy' ? 'bg-[#EC4899]' : 'bg-[#F59E0B]'
                            }`} />
                            <span className="truncate">{n.name}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Center Canvas */}
        <div 
          className={`flex-1 relative overflow-hidden transition-colors duration-200 ${actualTheme === 'dark' ? 'bg-[#07111F]' : 'bg-[#F8FAFC]'}`} 
          ref={containerRef}
          style={{
            backgroundImage: actualTheme === 'dark' 
              ? 'radial-gradient(circle at center, rgba(59, 130, 246, 0.08) 1px, transparent 1px)' 
              : 'radial-gradient(circle at center, rgba(100, 116, 139, 0.15) 1px, transparent 1px)',
            backgroundSize: '40px 40px'
          }}
        >
          {/* Ambient Lighting / Vignette */}
          <div className="absolute inset-0 pointer-events-none" style={{
            boxShadow: actualTheme === 'dark' ? 'inset 0 0 100px 20px rgba(0,0,0,0.7)' : 'inset 0 0 100px 20px rgba(255,255,255,0.7)'
          }} />

          {/* Subtle background ambient glows */}
          <div className="absolute top-1/4 left-1/4 w-[30vw] h-[30vw] bg-blue-500/5 rounded-full blur-[100px] pointer-events-none mix-blend-screen" />
          <div className="absolute bottom-1/4 right-1/4 w-[30vw] h-[30vw] bg-violet-500/5 rounded-full blur-[100px] pointer-events-none mix-blend-screen" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[40vw] h-[40vw] bg-emerald-500/5 rounded-full blur-[120px] pointer-events-none mix-blend-screen" />
          
          <div className="absolute right-4 bottom-4 z-10 flex flex-col gap-1 bg-surface/10 backdrop-blur-md border border-white/10 rounded-md p-1 shadow-2xl">
            <button className="p-2 hover:bg-white/10 rounded text-gray-400 hover:text-white transition-colors" onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 1.2)}>
              <ZoomIn size={16} />
            </button>
            <button className="p-2 hover:bg-white/10 rounded text-gray-400 hover:text-white transition-colors" onClick={() => graphRef.current?.zoom(graphRef.current.zoom() / 1.2)}>
              <ZoomOut size={16} />
            </button>
            <button className="p-2 hover:bg-white/10 rounded text-gray-400 hover:text-white transition-colors" onClick={() => graphRef.current?.zoomToFit(400)}>
              <Maximize size={16} />
            </button>
          </div>
          
          <ForceGraph2D
            ref={graphRef as any}
            width={dimensions.width}
            height={dimensions.height}
            graphData={processedGraphData}
            nodeLabel={() => ''}
            linkColor={(link: any) => {
              const srcId = typeof link.source === 'object' ? link.source.id : link.source;
              const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
              
              const isSelected = selectedNodeId === srcId || selectedNodeId === tgtId;
              const isHovered = hoverNode === srcId || hoverNode === tgtId;
              const hasFocus = selectedNodeId || hoverNode;
              
              if (hasFocus && !isSelected && !isHovered) {
                return actualTheme === 'dark' ? 'rgba(55, 65, 81, 0.1)' : 'rgba(148, 163, 184, 0.1)'; // Dimmed
              }
              
              if (isSelected) return actualTheme === 'dark' ? 'rgba(37, 99, 235, 0.8)' : 'rgba(37, 99, 235, 0.8)'; // Strong highlight
              if (isHovered) return actualTheme === 'dark' ? 'rgba(156, 163, 175, 0.6)' : 'rgba(100, 116, 139, 0.6)'; // Hover highlight
              
              return actualTheme === 'dark' ? 'rgba(55, 65, 81, 0.4)' : 'rgba(148, 163, 184, 0.4)'; // Normal edge
            }}
            linkWidth={(link: any) => {
              const srcId = typeof link.source === 'object' ? link.source.id : link.source;
              const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
              if (selectedNodeId === srcId || selectedNodeId === tgtId) return 2;
              if (hoverNode === srcId || hoverNode === tgtId) return 1.5;
              return 0.5; // Thin default
            }}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            onNodeClick={handleNodeClick}
            onNodeHover={(node) => setHoverNode(node ? node.id : null)}
            nodeCanvasObject={paintNode}
            backgroundColor="transparent"
            d3AlphaDecay={0.05}
            d3VelocityDecay={layout !== 'Force Graph' ? 0.9 : 0.4}
          />
        </div>

        {/* Right Inspector */}
        <div className="w-80 border-l border-border bg-surface shrink-0 flex flex-col relative z-20">
          <div className="h-12 border-b border-border flex items-center px-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Inspector</h2>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
            {!selectedNodeId ? (
              <div className="h-full flex flex-col items-center justify-center text-text-muted text-sm space-y-4">
                <Network size={48} className="text-border" />
                <p>Select a node to inspect it</p>
              </div>
            ) : contextLoading ? (
              <div className="space-y-4 animate-pulse">
                <div className="h-6 bg-surface-highlight rounded w-1/2"></div>
                <div className="h-4 bg-surface-highlight rounded w-3/4"></div>
                <div className="h-32 bg-surface-highlight rounded w-full"></div>
              </div>
            ) : contextData ? (
              <div className="space-y-6">
                <div>
                  <h3 className="text-xl font-bold text-text-main mb-1">{contextData.entity.name}</h3>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-text-muted bg-surface-highlight px-1.5 py-0.5 rounded border border-border">{contextData.entity.id}</span>
                    <span className="text-[10px] uppercase font-bold text-primary px-2 py-0.5 rounded bg-primary/10 border border-primary/20">
                      {contextData.entity.type}
                    </span>
                  </div>
                </div>
                
                {contextData.entity.description && (
                  <p className="text-sm text-text-muted leading-relaxed">
                    {contextData.entity.description}
                  </p>
                )}
                
                {/* Quantitative Metrics if populated by backend */}
                {contextData.entity.metrics && Object.keys(contextData.entity.metrics).length > 0 && (
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-text-muted mb-3 border-b border-border pb-2">Quantitative Metrics</h4>
                    <div className="grid grid-cols-2 gap-3">
                      {Object.entries(contextData.entity.metrics).map(([k, v]) => (
                        <div key={k} className="bg-surface-highlight p-3 rounded border border-border">
                          <div className="text-[10px] uppercase text-text-muted mb-1">{k}</div>
                          <div className="text-sm font-medium text-text-main">{String(v)}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Relationships */}
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-text-muted mb-3 border-b border-border pb-2">Relationships</h4>
                  <div className="space-y-2">
                    {contextData.relationships.map((rel, i) => {
                      const isSource = rel.source === selectedNodeId || (rel.source as any).id === selectedNodeId;
                      const targetId = isSource ? (rel.target as any).id || rel.target : (rel.source as any).id || rel.source;
                      const relatedNode = contextData.related_entities.find(n => n.id === targetId);
                      
                      if (!relatedNode) return null;
                      
                      const relLabel = rel.type.replace(/_/g, ' ');
                      
                      return (
                        <button 
                          key={i} 
                          onClick={() => handleNodeClick(relatedNode)}
                          className="w-full flex items-center justify-between p-2 rounded bg-surface-highlight hover:bg-surface-hover border border-border transition-colors group text-left"
                        >
                          <div className="flex flex-col">
                            <span className="text-[9px] uppercase font-semibold text-text-muted mb-0.5">
                              {isSource ? relLabel : `IS ${relLabel} OF`}
                            </span>
                            <span className="text-sm text-text-main font-medium flex items-center gap-2">
                              {relatedNode.name}
                            </span>
                          </div>
                          <ArrowRight size={14} className="text-text-muted group-hover:text-text-main" />
                        </button>
                      );
                    })}
                  </div>
                </div>
                
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
