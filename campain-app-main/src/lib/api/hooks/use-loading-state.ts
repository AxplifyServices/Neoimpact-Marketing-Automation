import { useLoading } from '@/context/loadingContext';
import { useEffect, useRef } from 'react';

export function useLoadingState(
  isLoading: boolean,
  shouldShowLoader: boolean,
  loadingKey: string
) {
  const { startLoading, stopLoading } = useLoading();
  const loadingKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!shouldShowLoader) return;

    if (isLoading) {
      if (!loadingKeyRef.current) {
        loadingKeyRef.current = loadingKey;
        startLoading(loadingKey);
      }
    } else {
      if (loadingKeyRef.current) {
        stopLoading(loadingKeyRef.current);
        loadingKeyRef.current = null;
      }
    }

    return () => {
      if (loadingKeyRef.current) {
        stopLoading(loadingKeyRef.current);
        loadingKeyRef.current = null;
      }
    };
  }, [isLoading, shouldShowLoader, loadingKey, startLoading, stopLoading]);
}