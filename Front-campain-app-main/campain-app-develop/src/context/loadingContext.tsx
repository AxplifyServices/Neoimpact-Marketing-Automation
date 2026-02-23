import { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';

interface LoadingContextType {
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  startLoading: (key: string) => void;
  stopLoading: (key: string) => void;
}

const LoadingContext = createContext<LoadingContextType | undefined>(undefined);

export function LoadingProvider({ children }: { children: ReactNode }) {
  const [isLoading, setIsLoading] = useState(false);
  const [loadingKeys] = useState(new Set<string>());

  const startLoading = (key: string) => {
    loadingKeys.add(key);
    setIsLoading(loadingKeys.size > 0);
  };

  const stopLoading = (key: string) => {
    loadingKeys.delete(key);
    setIsLoading(loadingKeys.size > 0);
  };

  return (
    <LoadingContext.Provider value={{ isLoading, setIsLoading, startLoading, stopLoading }}>
      {children}
    </LoadingContext.Provider>
  );
}

export function useLoadingContext() {
  const context = useContext(LoadingContext);
  if (!context) {
    throw new Error('useLoadingContext must be used within LoadingProvider');
  }
  return context;
}

export function useLoading() {
  return useLoadingContext();
}
