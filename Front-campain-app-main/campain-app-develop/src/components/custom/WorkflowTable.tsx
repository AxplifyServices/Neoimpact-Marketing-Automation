import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getApiClient } from '@/lib/api/api-client';
import { dashboardApi } from '@/lib/api/definitions/dashboard.api';
import type { DashboardComputeByCampaignResponse, CampaignGraphNode, ChannelTableRow } from '@/types/dashboard.types';
import type { Block } from '@/types/modele.types';

interface WorkflowTableProps {
  blocks: Block[];
  campaignId: string;
  getBlockDisplayNumber: (blockId: string) => number;
  etatsCampagne?: string[];
  dateMin?: string | null;
  dateMax?: string | null;
}

function formatObjectiveDetail(cond: Block['objectiveConditions'][number]): { name: string; value: string } {
  if (cond.type === 'client_field' && cond.clientField) {
    const name = cond.clientField;
    return { name, value: cond.clientFieldValue != null ? String(cond.clientFieldValue) : '' };
  }
  if (cond.type === 'client_filter' && cond.column) {
    const name = cond.column;
    const values = (cond.values || []).filter(Boolean);
    const min = (cond.min ?? '').toString().trim();
    const max = (cond.max ?? '').toString().trim();
    if (values.length > 0) return { name, value: values.join(', ') };
    if (min && max) return { name, value: `${min}-${max}` };
    if (min) return { name, value: `>= ${min}` };
    if (max) return { name, value: `<= ${max}` };
    return { name, value: '' };
  }
  const name = cond.column || cond.clientField || '?';
  return { name, value: '' };
}

export default function WorkflowTable({ blocks, campaignId, getBlockDisplayNumber, etatsCampagne, dateMin, dateMax }: WorkflowTableProps) {
  const apiClient = getApiClient();

  const { data: analyticsData } = useQuery<DashboardComputeByCampaignResponse>({
    queryKey: ['campaign-analytics-by-campaign', campaignId, etatsCampagne, dateMin, dateMax],
    queryFn: () => apiClient.request<DashboardComputeByCampaignResponse>(
      dashboardApi.computeByCampaign({ campagne_ids: [campaignId], etats_campagne: etatsCampagne, date_min: dateMin, date_max: dateMax })
    ),
    enabled: !!campaignId,
    staleTime: 5 * 60 * 1000,
  });

  const graphNodeMap = useMemo(() => {
    if (!analyticsData?.graph?.nodes) return new Map<string, CampaignGraphNode>();
    const map = new Map<string, CampaignGraphNode>();
    analyticsData.graph.nodes.forEach(node => map.set(String(node.id), node));
    return map;
  }, [analyticsData]);

  const channelStatsMap = useMemo(() => {
    if (!analyticsData?.tables?.by_channel) return new Map<string, ChannelTableRow>();
    const map = new Map<string, ChannelTableRow>();
    analyticsData.tables.by_channel.forEach(row => {
      if (row.Canal && row.Canal !== 'Total') map.set(row.Canal, row);
    });
    return map;
  }, [analyticsData]);

  const sortedBlocks = useMemo(
    () => [...blocks].sort((a, b) => getBlockDisplayNumber(a.id) - getBlockDisplayNumber(b.id)),
    [blocks, getBlockDisplayNumber],
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
            <th className="px-3 py-2 w-10">#</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Détails</th>
            <th className="px-3 py-2 text-right">Clients</th>
            <th className="px-3 py-2 text-right">Contacté</th>
            <th className="px-3 py-2 text-right">Convertis</th>
            <th className="px-3 py-2 text-right">Taux</th>
          </tr>
        </thead>
        <tbody>
          {sortedBlocks.map(block => {
            const num = getBlockDisplayNumber(block.id);
            const nodeId = block.id.replace(/^block_/, '');
            const graphNode = graphNodeMap.get(nodeId);
            const channelStats = channelStatsMap.get(block.canal);
            const isObjectif = block.isObjectif;

            return (
              <tr
                key={block.id}
                className={`border-b border-gray-100 ${isObjectif ? 'bg-emerald-50' : ''}`}
              >
                <td className="px-3 py-2 font-medium text-gray-500">{num}</td>
                <td className="px-3 py-2">
                  {isObjectif ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700 font-medium">
                      <span className="text-emerald-500">&#9670;</span> Objectif
                    </span>
                  ) : (
                    <span className="font-medium text-gray-900">{block.canal || '—'}</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {isObjectif ? (
                    <div className="flex flex-wrap items-center gap-1">
                      {block.objectiveConditions.map((cond, idx) => {
                        const detail = formatObjectiveDetail(cond);
                        return (
                          <span key={cond.id || idx} className="inline-flex items-center gap-1">
                            {idx > 0 && (
                              <span className="rounded-full bg-emerald-100 px-1.5 py-0 text-[10px] font-semibold text-emerald-600">
                                {block.objectiveOperator}
                              </span>
                            )}
                            <span className="text-emerald-700">{detail.name}</span>
                            {detail.value && (
                              <span className="font-semibold text-emerald-900">= {detail.value}</span>
                            )}
                          </span>
                        );
                      })}
                      {block.objectiveConditions.length === 0 && (
                        <span className="text-gray-400">—</span>
                      )}
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-right font-medium">
                  {graphNode ? graphNode.count.toLocaleString('fr-FR') : '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  {!isObjectif && channelStats
                    ? channelStats.Clients_contactes.toLocaleString('fr-FR')
                    : '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  {isObjectif && graphNode
                    ? graphNode.converted_count.toLocaleString('fr-FR')
                    : '—'}
                </td>
                <td className="px-3 py-2 text-right font-semibold">
                  {isObjectif && graphNode && graphNode.count > 0
                    ? `${((graphNode.converted_count / graphNode.count) * 100).toFixed(1)}%`
                    : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
