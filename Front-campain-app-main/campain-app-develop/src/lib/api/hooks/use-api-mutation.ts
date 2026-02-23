import { useMutation } from '@tanstack/react-query';
import type { UseMutationOptions } from '@tanstack/react-query';
import { useRef } from 'react';
import { useLoadingState } from './use-loading-state';
import type { ApiRequest, ApiError } from '../ApiRequest';
import { useApiClient } from './use-api-client';

// Pattern 1: Dynamic request with request function
export function useApiMutation<TData = any, TVariables = any>(
  options: Omit<UseMutationOptions<TData, ApiError, TVariables>, 'mutationFn'> & {
    request: (variables: TVariables) => ApiRequest;
    useLoader?: boolean;
  },
) {
  const apiClient = useApiClient();
  const requestRef = useRef<ApiRequest | null>(null);
  const loadingKeyRef = useRef(`mutation-${Date.now()}-${Math.random()}`);

  const mutation = useMutation<TData, ApiError, TVariables>({
    mutationFn: async (variables) => {
      const apiRequest = options.request(variables);
      requestRef.current = apiRequest;
      return apiClient.request<TData>(apiRequest);
    },
    ...options,
  });

  const shouldShowLoader =
    requestRef.current?.useLoader === true ||
    options?.useLoader === true;

  useLoadingState(
    mutation.isPending,
    shouldShowLoader,
    loadingKeyRef.current
  );

  return mutation;
}

// Pattern 2: Pre-configured request
export function useApiMutationWithRequest<TData = any, TVariables = any>(
  request: ApiRequest,
  options?: Omit<UseMutationOptions<TData, ApiError, TVariables>, 'mutationFn'> & {
    useLoader?: boolean;
  }
) {
  const apiClient = useApiClient();
  const loadingKeyRef = useRef(`mutation-${request.url}-${Date.now()}`);

  const mutation = useMutation<TData, ApiError, TVariables>({
    mutationFn: async (variables) => {
      return apiClient.request<TData>({
        ...request,
        body: variables
      });
    },
    ...options,
  });

  const shouldShowLoader = request.useLoader === true || options?.useLoader === true;

  useLoadingState(
    mutation.isPending,
    shouldShowLoader,
    loadingKeyRef.current
  );

  return mutation;
}
