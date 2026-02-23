import { useState, useMemo, useCallback } from 'react';
import { Phone, Target, Activity, Filter, AlertCircle, LayoutGrid, Table2 } from 'lucide-react';
import {
  BarChart,
  Bar,
  Funnel,
  FunnelChart,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { useDashboardData } from './useDashboardData';
import DashboardFilters from '@/components/custom/DashboardFilters';
import WorkflowPreview from '@/components/custom/WorkflowPreview';
import WorkflowTable from '@/components/custom/WorkflowTable';
import LoadingSpinner from '@/components/LoadingSpinner';
import Toast from '@/components/Toast';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { getApiClient } from '@/lib/api/api-client';
import { normalizeBlocks } from '@/lib/modele-normalization';
import { getBlockDisplayNumber } from '@/lib/block-utils';
import { dashboardApi } from '@/lib/api/definitions/dashboard.api';
import type { DashboardComputeRequest, DashboardComputeByCampaignResponse, ChannelTableRow } from '@/types/dashboard.types';

export default function DashboardPage() {
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [appliedFilters, setAppliedFilters] = useState<DashboardComputeRequest | undefined>();
  const [selectedCanal, setSelectedCanal] = useState<string | null>(null);
  const [workflowView, setWorkflowView] = useState<'graph' | 'table'>('graph');
  const [toast, setToast] = useState<{
    isOpen: boolean;
    title: string;
    message?: string;
    type?: 'success' | 'error' | 'warning';
  }>({
    isOpen: false,
    title: '',
  });

  const {
    filterOptions,
    filtersLoading,
    dashboardData,
    dataLoading,
    error,
  } = useDashboardData({
    selectedStates,
    appliedFilters,
  });

  const apiClient = getApiClient();

  const handleApplyFilters = useCallback((filters: DashboardComputeRequest) => {
    setAppliedFilters(filters);
    setSelectedCanal(null);
  }, []);

  const handleSelectionChange = useCallback((_campaigns: string[], states: string[]) => {
    setSelectedStates(states);
    setSelectedCanal(null);
  }, []);

  // Fetch model for workflow visualization
  const modeleId = dashboardData?.graph?.modele_id;
  const workflowCampaignId = dashboardData?.graph?.campaign_id;
  const { data: modele } = useQuery({
    queryKey: ['modele', modeleId],
    queryFn: () => apiClient.request<{ liste_action?: string; blocks?: unknown }>(modelesApi.findById(modeleId!)),
    enabled: !!modeleId,
  });

  // Pre-fetch analytics so WorkflowPreview has data in cache on first render
  const dateMin = appliedFilters?.date_min ?? null;
  const dateMax = appliedFilters?.date_max ?? null;
  const etatsCampagne = appliedFilters?.etats_campagne;
  const { isLoading: workflowAnalyticsLoading } = useQuery<DashboardComputeByCampaignResponse>({
    queryKey: ['campaign-analytics-by-campaign', workflowCampaignId, etatsCampagne, dateMin, dateMax],
    queryFn: () => apiClient.request<DashboardComputeByCampaignResponse>(
      dashboardApi.computeByCampaign({
        campagne_ids: workflowCampaignId ? [workflowCampaignId] : [],
        etats_campagne: etatsCampagne,
        date_min: dateMin,
        date_max: dateMax,
      })
    ),
    enabled: !!workflowCampaignId,
    staleTime: 5 * 60 * 1000,
  });

  const workflowBlocks = useMemo(() => {
    if (!modele) return [];
    if (Array.isArray(modele.blocks)) return normalizeBlocks(modele.blocks);
    if (typeof modele.blocks === 'string' && modele.blocks.trim()) {
      try { return normalizeBlocks(JSON.parse(modele.blocks)); } catch { /* */ }
    }
    if (typeof modele.liste_action === 'string' && modele.liste_action.trim()) {
      try { return normalizeBlocks(JSON.parse(modele.liste_action)); } catch { /* */ }
    }
    return [];
  }, [modele]);

  const blockDisplayNumber = useCallback((blockId: string) => {
    return getBlockDisplayNumber(workflowBlocks, blockId);
  }, [workflowBlocks]);

  // Transform KPIs to stat cards
  const stats = useMemo(() => {
    if (!dashboardData?.kpis) return [];

    const { kpis } = dashboardData;

    return [
      {
        title: 'Traitements',
        value: kpis.traitements_total.toLocaleString('fr-FR'),
        icon: <Activity className="w-4 h-4" />,
        bgColor: 'bg-amber-50',
        iconColor: 'text-amber-600',
        secondaryValue: '',
        secondaryLabel: '',
      },
      {
        title: 'Taux contact',
        value: `${(kpis.taux_contact_total * 100).toFixed(1)}%`,
        icon: <Phone className="w-4 h-4" />,
        bgColor: 'bg-cyan-50',
        iconColor: 'text-cyan-600',
        secondaryValue: '',
        secondaryLabel: '',
      },
      {
        title: 'Convertis',
        value: `${(kpis.taux_closing_sur_affectes * 100).toFixed(1)}%`,
        icon: <Target className="w-4 h-4" />,
        bgColor: 'bg-indigo-50',
        iconColor: 'text-indigo-600',
        secondaryValue: '',
        secondaryLabel: '',
      },
    ];
  }, [dashboardData]);

  const conversionFunnelData = useMemo(() => {
    if (!dashboardData?.kpis) return [];

    const { kpis } = dashboardData;

    return [
      { name: 'Transmis', value: kpis.transmis, fill: '#3b82f6' },
      { name: 'Contactes', value: kpis.contactes_total, fill: '#22c55e' },
      { name: 'Convertis', value: kpis.closing_total, fill: '#f59e0b' },
    ];
  }, [dashboardData]);

  const channelMetrics = useMemo(() => [
    {
      key: 'Traitements' as const,
      label: 'Traitements',
      formatter: (value: number) => value.toLocaleString('fr-FR'),
    },
    {
      key: 'Clients_contactes' as const,
      label: 'Clients contactes',
      formatter: (value: number) => value.toLocaleString('fr-FR'),
    },
    {
      key: 'Closing' as const,
      label: 'Convertis',
      formatter: (value: number) => value.toLocaleString('fr-FR'),
    },
    {
      key: 'Taux_closing_sur_traitements' as const,
      label: 'Taux convertis',
      formatter: (value: number) => `${(value * 100).toFixed(2)}%`,
    },
    {
      key: 'Taux_contact_sur_transmis' as const,
      label: 'Taux contact',
      formatter: (value: number) => `${(value * 100).toFixed(2)}%`,
    },
  ], []);

  // Transform series data for charts
  const regionChartData = useMemo(() => {
    if (!dashboardData?.series.region_transmit_closed) return [];
    return dashboardData.series.region_transmit_closed.map(item => ({
      name: item.Region,
      transmis: item.Transmis,
      closed: item.Closed,
    }));
  }, [dashboardData]);

  const dailyTrendsData = useMemo(() => {
    if (!dashboardData?.series.daily_treatments_closed) return [];
    return dashboardData.series.daily_treatments_closed.map(item => ({
      date: new Date(item.Date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' }),
      traitements: item.Traitements,
      closed: item.Closed,
    }));
  }, [dashboardData]);

  const channelData: ChannelTableRow[] = dashboardData?.tables.by_channel ?? [];
  const visibleChannelData = useMemo(
    () => channelData.filter(row => String(row.Canal).toLowerCase() !== 'total'),
    [channelData]
  );
  const selectedChannel = useMemo(
    () => visibleChannelData.find(row => row.Canal === selectedCanal) || null,
    [visibleChannelData, selectedCanal]
  );
  const canalColors = ['#1d4ed8', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#0ea5e9'];
  const canalColorMap = useMemo(() => {
    const map = new Map<string, string>();
    visibleChannelData.forEach((row, index) => {
      map.set(row.Canal, canalColors[index % canalColors.length]);
    });
    return map;
  }, [visibleChannelData, canalColors]);
  const pieData = useMemo(() => (
    visibleChannelData.map(row => ({
      name: row.Canal,
      value: row.Traitements,
    }))
  ), [visibleChannelData]);

  // Error handling
  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 p-3 sm:p-4 lg:p-6 pt-16 lg:pt-6">
        <div className="max-w-7xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 flex items-start gap-4">
            <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-lg font-semibold text-red-900 mb-1">Erreur de chargement</h3>
              <p className="text-red-700">Impossible de charger les données du dashboard. Veuillez réessayer plus tard.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-3 sm:p-4 lg:p-6 pt-16 lg:pt-6">
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">Dashboard</h1>
        <p className="text-gray-600 text-xs sm:text-sm">Vue d'ensemble des performances de vos campagnes</p>
      </div>

      {/* Filters */}
      {filtersLoading ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-8">
          <LoadingSpinner size="sm" />
          <p className="text-gray-500 text-xs mt-2">Chargement des filtres...</p>
        </div>
      ) : (
        <DashboardFilters
          filterOptions={filterOptions}
          onApplyFilters={handleApplyFilters}
          onSelectionChange={handleSelectionChange}
          isLoading={dataLoading}
        />
      )}

      {/* Loading State */}
      {dataLoading && (
        <div className="flex flex-col items-center justify-center py-20">
          <LoadingSpinner size="lg" />
          <p className="text-gray-600 mt-4">Calcul des statistiques en cours...</p>
        </div>
      )}

      {/* Data Display - Only when data is loaded */}
      {!dataLoading && dashboardData && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            {stats.map((stat, index) => (
              <div key={index} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                <div className={`p-2 ${stat.bgColor} rounded-lg inline-flex mb-4`}>
                  <div className={stat.iconColor}>{stat.icon}</div>
                </div>
                <h3 className="text-xs text-gray-600 mb-2">{stat.title}</h3>
                <div className="text-2xl font-bold text-gray-900 mb-2">{stat.value}</div>
                {stat.secondaryValue && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gray-900">{stat.secondaryValue}</span>
                    <span className="text-xs text-gray-500">{stat.secondaryLabel}</span>
                  </div>
                )}
              </div>
            ))}
          </div>

          {conversionFunnelData.length > 0 && (
            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 mb-8">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-gray-900">Funnel de conversion</h2>
                <span className="text-xs text-gray-500">Campagne selectionnee</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
                <div className="space-y-4">
                  {conversionFunnelData.map((stage, index) => {
                    const baseValue = conversionFunnelData[0]?.value || 0;
                    const percent = baseValue > 0 ? Math.round((stage.value / baseValue) * 100) : 0;
                    return (
                      <div key={stage.name} className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <span
                            className="w-2.5 h-2.5 rounded-full"
                            style={{ backgroundColor: stage.fill }}
                          />
                          <span className="text-sm font-medium text-gray-700">{stage.name}</span>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-semibold text-gray-900">
                            {stage.value.toLocaleString('fr-FR')}
                          </div>
                          <div className="text-xs text-gray-500">
                            {index === 0 ? '100%' : `${percent}%`}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  <div className="pt-3 border-t border-gray-100 text-sm text-gray-600">
                    Taux global: {((dashboardData.kpis.taux_closing_sur_affectes || 0) * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <FunnelChart>
                      <Funnel dataKey="value" data={conversionFunnelData} isAnimationActive={false} />
                    </FunnelChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}

          {/* Workflow Section - Full Width */}
          {dashboardData?.graph && workflowBlocks.length > 0 && !workflowAnalyticsLoading && (
            <div className="mb-8">
              <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-lg font-bold text-gray-900">Workflow Campagne</h2>
                    <p className="text-xs text-gray-500">{dashboardData.graph.modele_nom}</p>
                  </div>
                  <div className="flex items-center rounded-lg border border-gray-200 overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setWorkflowView('graph')}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${
                        workflowView === 'graph'
                          ? 'bg-slate-900 text-white'
                          : 'bg-white text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      <LayoutGrid className="w-3.5 h-3.5" />
                      Workflow
                    </button>
                    <button
                      type="button"
                      onClick={() => setWorkflowView('table')}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${
                        workflowView === 'table'
                          ? 'bg-slate-900 text-white'
                          : 'bg-white text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      <Table2 className="w-3.5 h-3.5" />
                      Tableau
                    </button>
                  </div>
                </div>
                {workflowView === 'graph' ? (
                  <div style={{ height: '500px' }} className="border border-gray-200 rounded-lg overflow-hidden">
                    <WorkflowPreview
                      blocks={workflowBlocks}
                      getBlockDisplayNumber={blockDisplayNumber}
                      campaignId={dashboardData.graph.campaign_id}
                      etatsCampagne={etatsCampagne}
                      dateMin={dateMin}
                      dateMax={dateMax}
                      showHeader={false}
                      showFrame={false}
                      height={500}
                      containerClassName="rounded-lg"
                    />
                  </div>
                ) : (
                  <WorkflowTable
                    blocks={workflowBlocks}
                    campaignId={dashboardData.graph.campaign_id}
                    etatsCampagne={etatsCampagne}
                    dateMin={dateMin}
                    dateMax={dateMax}
                    getBlockDisplayNumber={blockDisplayNumber}
                  />
                )}
              </div>
            </div>
          )}

          {/* Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {/* Region Chart */}
            {regionChartData.length > 0 && (
              <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                <h2 className="text-lg font-bold text-gray-900 mb-6">Distribution par Région</h2>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={regionChartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" />
                    <YAxis dataKey="name" type="category" width={150} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="transmis" fill="#3b82f6" name="Transmis" />
                    <Bar dataKey="closed" fill="#10b981" name="Conversions" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Channel Performance */}
            {visibleChannelData.length > 0 && (
              <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                {selectedCanal && selectedChannel ? (
                  <>
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h2 className="text-xl font-bold text-gray-900">Performance par Canal</h2>
                        <p className="text-sm text-gray-500">Canal: {selectedCanal}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSelectedCanal(null)}
                        className="text-xs font-semibold text-gray-600 hover:text-gray-900"
                      >
                        Retour au graphique
                      </button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {channelMetrics.map((metric) => (
                        <div key={`${selectedCanal}-${metric.key}`} className="rounded-xl border border-gray-100 bg-gray-50/60 p-4">
                          <div className="text-xs text-gray-500 mb-2">{metric.label}</div>
                          <div className="text-xl font-semibold text-gray-900">
                            {metric.formatter(selectedChannel[metric.key] as number)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h2 className="text-xl font-bold text-gray-900">Performance par Canal</h2>
                        <p className="text-sm text-gray-500">Cliquez sur un canal pour voir les details</p>
                      </div>
                      <span className="text-xs text-gray-500">Base sur Traitements</span>
                    </div>
                    <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-6 items-center">
                      <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={pieData}
                              dataKey="value"
                              nameKey="name"
                              innerRadius={60}
                              outerRadius={95}
                              paddingAngle={2}
                              stroke="white"
                              strokeWidth={2}
                              isAnimationActive={false}
                              onClick={(entry: { name?: string }) => {
                                const name = entry?.name;
                                if (name) {
                                  setSelectedCanal(name);
                                }
                              }}
                            >
                              {pieData.map((entry, index) => {
                                const color = canalColorMap.get(entry.name) ?? canalColors[index % canalColors.length];
                                return <Cell key={`canal-${entry.name}`} fill={color} cursor="pointer" />;
                              })}
                            </Pie>
                            <Tooltip
                              formatter={(value) => {
                                const numericValue = typeof value === 'number' ? value : Number(value);
                                return numericValue.toLocaleString('fr-FR');
                              }}
                              labelFormatter={(label) => `Canal: ${label}`}
                            />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="space-y-2">
                        {pieData.map((entry, index) => {
                          const color = canalColorMap.get(entry.name) ?? canalColors[index % canalColors.length];
                          return (
                            <button
                              key={`legend-${entry.name}`}
                              type="button"
                              onClick={() => setSelectedCanal(entry.name)}
                              className="w-full flex items-center justify-between gap-3 rounded-xl border border-gray-100 bg-gray-50/60 px-3 py-2 text-left hover:bg-gray-100 transition-colors"
                            >
                              <div className="flex items-center gap-2">
                                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                                <span className="text-sm font-semibold text-gray-800">{entry.name}</span>
                              </div>
                              <span className="text-xs font-semibold text-gray-900">
                                {entry.value.toLocaleString('fr-FR')}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Daily Trends Chart */}
          {dailyTrendsData.length > 0 && (
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <h2 className="text-xl font-bold text-gray-900 mb-6">Évolution Quotidienne</h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={dailyTrendsData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="traitements" stroke="#3b82f6" strokeWidth={2} name="Traitements" />
                  <Line type="monotone" dataKey="closed" stroke="#10b981" strokeWidth={2} name="Conversions" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

        </>
      )}

      {/* Empty State - No filters applied */}
      {!appliedFilters && !dataLoading && (
        <div className="text-center py-20">
          <Filter className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Aucun filtre appliqué</h3>
          <p className="text-gray-500">Sélectionnez des filtres pour afficher les données du dashboard</p>
        </div>
      )}
    </div>
  );
}
