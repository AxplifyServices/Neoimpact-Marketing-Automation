import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queuesApi } from '@/lib/api/definitions/queues.api';
import { getApiClient } from '@/lib/api/api-client';
import type { QueueContact } from '@/types/campaign.types';

export function useCRCData(id_campagne?: string | null) {
  const apiClient = getApiClient();
  const queryClient = useQueryClient();

  // Fetch next contact from queue
  const {
    data: contact,
    isLoading,
    error,
    refetch: fetchNext,
  } = useQuery<QueueContact | null>({
    queryKey: ['crc-next', id_campagne],
    queryFn: () => apiClient.request<QueueContact>(queuesApi.getNext('crc', id_campagne)),
    retry: false,  // Don't retry if queue is empty
  });

  // Apply result mutation
  const applyResultMutation = useMutation({
    mutationFn: (data: { resultat: string }) =>
      apiClient.request(
        queuesApi.applyResult('crc', {
          id_campagne: contact?.context.id_campagne!,
          radical_compte: contact?.context.radical_compte!,
          resultat: data.resultat,
        })
      ),
    onSuccess: () => {
      // Fetch next contact after applying result
      queryClient.invalidateQueries({ queryKey: ['crc-next', id_campagne] });
    },
  });

  // Skip mutation
  const skipMutation = useMutation({
    mutationFn: () =>
      apiClient.request(
        queuesApi.skip('crc', {
          id_campagne: contact?.context.id_campagne!,
          radical_compte: contact?.context.radical_compte!,
        })
      ),
    onSuccess: () => {
      // Fetch next contact after skipping
      queryClient.invalidateQueries({ queryKey: ['crc-next', id_campagne] });
    },
  });

  // Initiate call mutation
  const callMutation = useMutation({
    mutationFn: () => apiClient.request(queuesApi.initiateCall()),
  });

  return {
    contact,
    isLoading,
    error,
    fetchNext,
    applyResult: applyResultMutation.mutate,
    skip: skipMutation.mutate,
    initiateCall: callMutation.mutate,
    isApplyingResult: applyResultMutation.isPending,
    isSkipping: skipMutation.isPending,
    isCalling: callMutation.isPending,
  };
}
