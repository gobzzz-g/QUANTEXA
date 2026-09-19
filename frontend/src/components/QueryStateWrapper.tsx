import React from 'react';
import { AlertTriangle, RefreshCw, Inbox } from 'lucide-react';

interface QueryStateWrapperProps<T> {
  isLoading: boolean;
  error: Error | null;
  data: T | undefined | null;
  onRetry?: () => void;
  loadingComponent?: React.ReactNode;
  emptyComponent?: React.ReactNode;
  children: (data: T) => React.ReactNode;
}

export function QueryStateWrapper<T>({
  isLoading,
  error,
  data,
  onRetry,
  loadingComponent,
  emptyComponent,
  children
}: QueryStateWrapperProps<T>) {
  if (isLoading) {
    return loadingComponent ? (
      <>{loadingComponent}</>
    ) : (
      <div className="flex flex-col items-center justify-center p-8 space-y-4 min-h-[200px] w-full h-full animate-pulse">
        <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
        <p className="text-muted text-sm font-medium">Loading data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 space-y-4 min-h-[200px] w-full h-full bg-danger/10 border border-danger/30 rounded-lg">
        <AlertTriangle className="w-12 h-12 text-danger" />
        <div className="text-center">
          <h3 className="text-lg font-bold text-danger mb-1">Data Fetch Error</h3>
          <p className="text-text-muted text-sm max-w-md">{error.message}</p>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="flex items-center gap-2 px-4 py-2 bg-surface hover:bg-surface-highlight border border-border rounded transition-colors text-sm font-medium"
          >
            <RefreshCw className="w-4 h-4" />
            Retry Request
          </button>
        )}
      </div>
    );
  }

  if (data === undefined || data === null || (Array.isArray(data) && data.length === 0)) {
    return emptyComponent ? (
      <>{emptyComponent}</>
    ) : (
      <div className="flex flex-col items-center justify-center p-8 space-y-4 min-h-[200px] w-full h-full text-muted">
        <Inbox className="w-12 h-12 opacity-50" />
        <p className="text-sm font-medium">No data available.</p>
      </div>
    );
  }

  return <>{children(data)}</>;
}
