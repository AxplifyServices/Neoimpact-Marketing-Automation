import { useQuery } from '@tanstack/react-query';
import type { UseQueryOptions } from '@tanstack/react-query';
import { useLoadingState } from './use-loading-state';
import type { ApiRequest, ApiError } from '../ApiRequest';
import { useApiClient } from './use-api-client';

export function useApiQuery<TData = any>(
    queryKey: any[],
    request: ApiRequest,
    options?: Omit<UseQueryOptions<TData, ApiError>, 'queryKey' | 'queryFn'> & {
        forceRefresh?: boolean;
        useLoader?: boolean;
    }
) {
    const apiClient = useApiClient();

    const shouldShowLoader =
        request.method === 'GET' &&
        (request.useLoader === true || options?.useLoader === true);

    const query = useQuery<TData, ApiError>({
        queryKey,
        queryFn: () => apiClient.request<TData>({
            ...request,
            headers: {
                ...request.headers,
                ...(options?.forceRefresh && {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                })
            }
        }),
        ...options,
    });

    useLoadingState(
        query.isFetching || query.isLoading,
        shouldShowLoader,
        queryKey.join('-')
    );

    return query;
}