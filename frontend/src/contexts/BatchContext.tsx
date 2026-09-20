import { createContext, useContext, useState, type ReactNode } from 'react';

interface BatchContextValue {
  selectedBatchId: string | null;
  setSelectedBatchId: (id: string | null) => void;
}

const BatchContext = createContext<BatchContextValue>({
  selectedBatchId: null,
  setSelectedBatchId: () => {},
});

export function BatchProvider({ children }: { children: ReactNode }) {
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  return (
    <BatchContext.Provider value={{ selectedBatchId, setSelectedBatchId }}>
      {children}
    </BatchContext.Provider>
  );
}

export function useBatch() {
  return useContext(BatchContext);
}
