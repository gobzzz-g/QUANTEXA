import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { ResearchResponse } from '../api/types';
import { Sparkles, Bot, User, CheckCircle2, Circle, ArrowRight } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { QueryStateWrapper } from '../components/QueryStateWrapper';

export function AiResearch() {
  const [query, setQuery] = useState<string>('Analyze BTC and NVIDIA from 2022 to 2026.');
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);

  const { data: research, isLoading, error } = useQuery<ResearchResponse>({
    queryKey: ['research', submittedQuery],
    queryFn: async () => (await apiClient.post('/research', { query: submittedQuery })).data,
    enabled: !!submittedQuery,
    staleTime: Infinity,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      setSubmittedQuery(query);
    }
  };

  return (
    <div className="flex flex-col h-full space-y-6 animate-fade-in">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI Research Agent</h1>
          <p className="text-sm text-text-muted mt-1">
            Orchestrate data collection, quantitative analysis, and knowledge graph insights via natural language.
          </p>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 flex-1 min-h-0">
        {/* LEFT: Conversation / Input Panel */}
        <div className="w-full lg:w-[350px] flex-shrink-0 flex flex-col h-[400px] lg:h-full gap-4">
          <Card className="flex-1 flex flex-col">
            <CardHeader className="py-3 border-b border-border">
              <CardTitle className="text-sm flex items-center">
                <Bot size={16} className="text-primary mr-2" />
                Research Assistant
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
              <div className="flex gap-3">
                <div className="w-6 h-6 rounded bg-primary/20 flex items-center justify-center flex-shrink-0 mt-1">
                  <Bot size={14} className="text-primary" />
                </div>
                <div className="bg-surface-hover p-3 rounded-lg rounded-tl-none text-sm text-text-main border border-border/50">
                  How can I assist your analysis today? I can orchestrate quantitative backtests, portfolio optimization, and cross-asset correlation.
                </div>
              </div>

              {submittedQuery && (
                <div className="flex gap-3 flex-row-reverse">
                  <div className="w-6 h-6 rounded bg-accent/20 flex items-center justify-center flex-shrink-0 mt-1">
                    <User size={14} className="text-accent" />
                  </div>
                  <div className="bg-accent/10 p-3 rounded-lg rounded-tr-none text-sm text-text-main border border-accent/20">
                    {submittedQuery}
                  </div>
                </div>
              )}

              {isLoading && (
                <div className="flex gap-3">
                  <div className="w-6 h-6 rounded bg-primary/20 flex items-center justify-center flex-shrink-0 mt-1">
                    <Bot size={14} className="text-primary" />
                  </div>
                  <div className="bg-surface-hover p-3 rounded-lg rounded-tl-none text-sm text-text-main border border-border/50">
                    <div className="flex items-center gap-2">
                      <Sparkles size={14} className="text-primary animate-pulse" />
                      <span className="animate-pulse">Orchestrating research workflow...</span>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
            
            <div className="p-3 border-t border-border">
              <form onSubmit={handleSubmit} className="relative">
                <input
                  type="text"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="Ask a research question..."
                  className="input-field w-full pr-10 bg-surface"
                  disabled={isLoading}
                />
                <button 
                  type="submit" 
                  disabled={isLoading || !query.trim()}
                  className="absolute right-1 top-1 bottom-1 px-2 text-text-muted hover:text-primary transition-colors disabled:opacity-50"
                >
                  <ArrowRight size={16} />
                </button>
              </form>
            </div>
          </Card>
        </div>

        {/* RIGHT: Results Panel */}
        <div className="flex-1 flex flex-col h-full min-h-[500px]">
          {!submittedQuery ? (
            <Card className="h-full flex items-center justify-center border-dashed">
              <div className="text-center max-w-md p-6">
                <Sparkles size={32} className="text-primary/50 mx-auto mb-4" />
                <h3 className="text-lg font-bold text-text-main mb-2">QuantExa Orchestrator</h3>
                <p className="text-sm text-text-muted">
                  The AI agent does not hallucinate financial metrics. It dynamically calls backend calculation tools and formats the deterministic results into a professional research report.
                </p>
              </div>
            </Card>
          ) : (
            <QueryStateWrapper
              isLoading={isLoading}
              error={error}
              data={research}
              onRetry={() => {}}
            >
              {(data) => (
                <div className="h-full flex flex-col gap-6 overflow-y-auto custom-scrollbar pr-2">
                  <Card>
                    <CardHeader className="py-3 border-b border-border">
                      <CardTitle className="text-sm">Orchestration Steps</CardTitle>
                    </CardHeader>
                    <CardContent className="p-4">
                      <div className="space-y-3">
                        {data.orchestration_steps.map((step, i) => (
                          <div key={i} className="flex items-center text-sm">
                            {step.status === 'success' ? (
                              <CheckCircle2 size={16} className="text-positive mr-3 flex-shrink-0" />
                            ) : (
                              <Circle size={16} className="text-text-muted mr-3 flex-shrink-0" />
                            )}
                            <div>
                              <span className="font-medium text-text-main mr-2">{step.step}:</span>
                              <span className="text-text-muted">{step.detail}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {data.findings.map((finding, i) => (
                      <Card key={i}>
                        <CardHeader className="py-2.5 border-b border-border bg-surface-hover/30">
                          <CardTitle className="text-xs uppercase tracking-wider text-primary">{finding.category}</CardTitle>
                        </CardHeader>
                        <CardContent className="p-4 text-sm text-text-main leading-relaxed">
                          {finding.content}
                        </CardContent>
                      </Card>
                    ))}
                  </div>

                  <Card className="border-l-4 border-l-accent">
                    <CardHeader className="py-3">
                      <CardTitle className="text-sm flex items-center">
                        <Sparkles size={16} className="text-accent mr-2" />
                        AI Conclusion
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-4 pt-0 text-sm font-medium leading-relaxed">
                      {data.conclusion}
                    </CardContent>
                  </Card>
                </div>
              )}
            </QueryStateWrapper>
          )}
        </div>
      </div>
    </div>
  );
}
