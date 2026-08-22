import { Search, TrendingUp, Users, Target, MoreVertical, Play, Pause, XCircle, X, Check, Copy, MapPin, Monitor } from 'lucide-react';
import { useCampagnesData } from './useCampagnesData';
import { lazy, Suspense, useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { campaignsApi } from '@/lib/api/definitions/campaigns.api';
import { getApiClient } from '@/lib/api/api-client';
import Toast from '../../components/Toast';
import ConfirmDialog from '../../components/ConfirmDialog';
import LoadingSpinner from '../../components/LoadingSpinner';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import type { CibleCommercialPressureSummary } from '@/types/commercial-pressure.types';

const CreateCampaignModal = lazy(() => import('../../components/custom/CreateCampaignModal'));
const WorkflowModal = lazy(() => import('../../components/custom/WorkflowModal'));

const updateCachedCampaignState = (queryClient: ReturnType<typeof useQueryClient>, id: string, etat: string) => {
  queryClient.setQueriesData({ queryKey: ['campaigns', 'infinite'] }, (oldData: any) => {
    if (!oldData?.pages) return oldData;
    return {
      ...oldData,
      pages: oldData.pages.map((page: any) => ({
        ...page,
        items: (page.items ?? []).map((item: any) =>
          item.id_campagne === id ? { ...item, etat_campagne: etat } : item
        ),
      })),
    };
  });
};

const markCampaignDependentCachesStale = (queryClient: ReturnType<typeof useQueryClient>) => {
  void queryClient.invalidateQueries({ queryKey: ['campaign-meta', 'active-choices'], refetchType: 'none' });
  void queryClient.invalidateQueries({ queryKey: ['dashboard-filters'], refetchType: 'none' });
  void queryClient.invalidateQueries({ queryKey: ['dashboard-compute'], refetchType: 'none' });
};

export default function CampagnesPage() {
  const queryClient = useQueryClient();
  const apiClient = getApiClient();
  const [searchQuery, setSearchQuery] = useState('');
  const deferredSearch = useDebouncedValue(searchQuery, 300);
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [dateMin, setDateMin] = useState<string>('');
  const [dateMax, setDateMax] = useState<string>('');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [cancelDialog, setCancelDialog] = useState<{ isOpen: boolean; campaignId?: string; campaignTitle?: string }>({
    isOpen: false,
  });
  const [activationPressureDialog, setActivationPressureDialog] = useState<{
    isOpen: boolean;
    campaignId?: string;
    campaignTitle?: string;
    pctEleve?: number;
  }>({ isOpen: false });
  const [workflowModal, setWorkflowModal] = useState<{
    isOpen: boolean;
    modelId?: string;
    campaignId?: string;
  }>({ isOpen: false });
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' | 'warning' }>({
    isOpen: false,
    title: '',
  });

  const {
    stats: statsData,
    campaigns,
    total,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useCampagnesData({
    search: deferredSearch,
    statuses: selectedStatuses,
    dateMin,
    dateMax,
  });

  const [duplicateCampaign, setDuplicateCampaign] = useState<typeof campaigns[0] | null>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);

  const prefetchCreateCampaign = useCallback(() => {
    void queryClient.prefetchQuery({
      queryKey: ['campaign-meta', 'create-options'],
      queryFn: () => apiClient.request(campaignsApi.createOptions()),
      staleTime: 5 * 60_000,
    });
    void import('../../components/custom/CreateCampaignModal');
  }, [apiClient, queryClient]);

  // Lifecycle mutations are optimistic: the card changes immediately while
  // the backend performs its single-row campaign update. On error we restore
  // the previous query cache exactly.
  const cancelCampaignMutation = useMutation({
    mutationFn: (id: string) => apiClient.request(campaignsApi.cancel(id)),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['campaigns'] });
      const snapshot = queryClient.getQueriesData({ queryKey: ['campaigns', 'infinite'] });
      updateCachedCampaignState(queryClient, id, 'Annulée');
      return { snapshot };
    },
    onSuccess: () => {
      markCampaignDependentCachesStale(queryClient);
      setToast({
        isOpen: true,
        title: 'Campagne annulée',
        message: `La campagne "${cancelDialog.campaignTitle}" a été annulée avec succès`,
        type: 'success',
      });
      setCancelDialog({ isOpen: false });
    },
    onError: (_error, _id, context) => {
      context?.snapshot?.forEach(([key, data]) => queryClient.setQueryData(key, data));
      setToast({ isOpen: true, title: 'Erreur', message: "Une erreur est survenue lors de l'annulation", type: 'error' });
    },
  });

  const pauseCampaignMutation = useMutation({
    mutationFn: (id: string) => apiClient.request(campaignsApi.pause(id)),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['campaigns'] });
      const snapshot = queryClient.getQueriesData({ queryKey: ['campaigns', 'infinite'] });
      updateCachedCampaignState(queryClient, id, 'En pause');
      return { snapshot };
    },
    onSuccess: () => {
      markCampaignDependentCachesStale(queryClient);
      setToast({ isOpen: true, title: 'Campagne désactivée', message: 'La campagne a été désactivée avec succès', type: 'success' });
      setOpenMenuId(null);
    },
    onError: (_error, _id, context) => {
      context?.snapshot?.forEach(([key, data]) => queryClient.setQueryData(key, data));
      setToast({ isOpen: true, title: 'Erreur', message: 'Une erreur est survenue', type: 'error' });
    },
  });

  const activateCampaignMutation = useMutation({
    mutationFn: (id: string) => apiClient.request<any>(campaignsApi.activate(id)),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['campaigns'] });
      const snapshot = queryClient.getQueriesData({ queryKey: ['campaigns', 'infinite'] });
      updateCachedCampaignState(queryClient, id, 'En cours');
      return { snapshot };
    },
    onSuccess: (data: any, _id, context) => {
      if (data && !data.ok && data.error) {
        context?.snapshot?.forEach(([key, value]) => queryClient.setQueryData(key, value));
        setToast({ isOpen: true, title: "Impossible d'activer", message: data.error, type: 'error' });
        return;
      }
      markCampaignDependentCachesStale(queryClient);
      setToast({ isOpen: true, title: 'Campagne activée', message: 'La campagne a été activée avec succès', type: 'success' });
      setOpenMenuId(null);
    },
    onError: (error: any, _id, context) => {
      context?.snapshot?.forEach(([key, value]) => queryClient.setQueryData(key, value));
      const errorMessage = error?.response?.data?.error || error?.message || 'Une erreur est survenue';
      setToast({ isOpen: true, title: 'Erreur', message: errorMessage, type: 'error' });
    },
  });

  const displayedCampaigns = campaigns;

  // Load the next backend page only when the user reaches the end of the loaded list.
  useEffect(() => {
    const currentRef = loadMoreRef.current;
    if (!currentRef || !hasNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const first = entries[0];
        if (first.isIntersecting && hasNextPage && !isLoading && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { rootMargin: '240px 0px', threshold: 0.01 }
    );

    observer.observe(currentRef);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, isLoading]);

  // Status options
  const statusOptions = useMemo(() => [
    { value: 'En cours', label: 'En cours', color: 'bg-green-100 text-green-700' },
    { value: 'En pause', label: 'En pause', color: 'bg-orange-100 text-orange-700' },
    { value: 'Planifié', label: 'Planifié', color: 'bg-yellow-100 text-yellow-700' },
    { value: 'Terminé', label: 'Terminé', color: 'bg-blue-100 text-blue-700' },
    { value: 'Annulée', label: 'Annulée', color: 'bg-gray-100 text-gray-500' },
  ], []);

  const handleNewCampaign = () => {
    prefetchCreateCampaign();
    setIsCreateModalOpen(true);
  };

  const handleResetFilters = () => {
    setSearchQuery('');
    setSelectedStatuses([]);
    setDateMin('');
    setDateMax('');
  };

  const toggleStatus = (value: string) => {
    setSelectedStatuses((prev) =>
      prev.includes(value) ? prev.filter((status) => status !== value) : [...prev, value]
    );
  };

  const hasActiveFilters = Boolean(searchQuery || selectedStatuses.length > 0 || dateMin || dateMax);

  const handleActivateCampaign = async (campaignId: string, campaignTitle: string) => {
    setOpenMenuId(null);
    try {
      const pressure = await apiClient.request<CibleCommercialPressureSummary>(campaignsApi.pressureSummary(campaignId));
      if (pressure.supported && pressure.warning) {
        setActivationPressureDialog({
          isOpen: true,
          campaignId,
          campaignTitle,
          pctEleve: pressure.pct_eleve,
        });
        return;
      }
      activateCampaignMutation.mutate(campaignId);
    } catch (error) {
      console.error('Error checking commercial pressure:', error);
      setToast({
        isOpen: true,
        title: 'Vérification impossible',
        message: "La pression commerciale de la campagne n'a pas pu être vérifiée.",
        type: 'error',
      });
    }
  };

  const confirmActivationDespitePressure = () => {
    if (activationPressureDialog.campaignId) {
      activateCampaignMutation.mutate(activationPressureDialog.campaignId);
    }
  };

  const handlePauseCampaign = (campaignId: string) => {
    setOpenMenuId(null);
    pauseCampaignMutation.mutate(campaignId);
  };

  const handleCancelCampaign = (campaignId: string, campaignTitle: string) => {
    setOpenMenuId(null);
    setCancelDialog({ isOpen: true, campaignId, campaignTitle });
  };

  const confirmCancel = () => {
    if (cancelDialog.campaignId) {
      cancelCampaignMutation.mutate(cancelDialog.campaignId);
    }
  };

  const handleOpenWorkflow = (campaign: any) => {
    setWorkflowModal({
      isOpen: true,
      modelId: campaign.id_modele,
      campaignId: campaign.id,
    });
  };



  const stats = [
    {
      icon: <TrendingUp className="w-4 h-4 text-blue-600" />,
      ...statsData[0],
    },
    {
      icon: <Users className="w-4 h-4 text-purple-600" />,
      ...statsData[1],
    },
    {
      icon: <Target className="w-4 h-4 text-green-600" />,
      ...statsData[2],
    },
  ];

  return (
    <div className="min-h-screen bg-gray-50 p-3 sm:p-4 lg:p-6 pt-16 lg:pt-6">
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />

      {isCreateModalOpen && (
        <Suspense fallback={null}>
          <CreateCampaignModal
            isOpen
            onClose={() => {
              setIsCreateModalOpen(false);
              setDuplicateCampaign(null);
            }}
            onSuccess={() => {
              setToast({
                isOpen: true,
                title: duplicateCampaign ? 'Campagne dupliquée' : 'Campagne créée',
                message: duplicateCampaign ? 'La campagne a été dupliquée avec succès' : 'La campagne a été créée avec succès',
                type: 'success',
              });
            }}
            duplicateData={duplicateCampaign ? {
              nom_campagne: duplicateCampaign.title,
              description: duplicateCampaign.description,
              id_modele: duplicateCampaign.id_modele,
              id_cible: duplicateCampaign.id_cible,
              date_debut: duplicateCampaign.startDate,
              date_fin: duplicateCampaign.endDate,
              type_campagne: duplicateCampaign.type_campagne,
              visitMode: duplicateCampaign.visitMode,
              visitPurpose: duplicateCampaign.visitPurpose,
            } : undefined}
          />
        </Suspense>
      )}

      <ConfirmDialog
        isOpen={cancelDialog.isOpen}
        onClose={() => setCancelDialog({ isOpen: false })}
        onConfirm={confirmCancel}
        title="Annuler la campagne"
        message={`Êtes-vous sûr de vouloir annuler la campagne "${cancelDialog.campaignTitle}" ? Cette action est irréversible.`}
        confirmText="Annuler la campagne"
        cancelText="Retour"
        type="danger"
      />

      <ConfirmDialog
        isOpen={activationPressureDialog.isOpen}
        onClose={() => setActivationPressureDialog({ isOpen: false })}
        onConfirm={confirmActivationDespitePressure}
        title="Pression commerciale élevée"
        message={`${Number(activationPressureDialog.pctEleve ?? 0).toFixed(1)} % des clients de la campagne "${activationPressureDialog.campaignTitle ?? ''}" sont actuellement en pression élevée. Êtes-vous certain de vouloir l'activer ?`}
        confirmText="Activer quand même"
        cancelText="Revoir la campagne"
        type="warning"
      />

      {workflowModal.isOpen && (
        <Suspense fallback={null}>
          <WorkflowModal
            isOpen
            onClose={() => setWorkflowModal({ isOpen: false })}
            modelId={workflowModal.modelId || ''}
            campaignId={workflowModal.campaignId}
          />
        </Suspense>
      )}


      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">Vos Campagnes</h1>
          <p className="text-gray-600 text-xs sm:text-sm">Gérez et suivez toutes vos campagnes marketing en un seul endroit</p>
        </div>
        <button
          type="button"
          onClick={handleNewCampaign}
          onMouseEnter={prefetchCreateCampaign}
          onFocus={prefetchCreateCampaign}
          onPointerDown={prefetchCreateCampaign}
          className="bg-slate-900 text-white px-4 py-2 rounded-xl font-medium hover:bg-slate-800 transition-colors flex items-center gap-2 cursor-pointer whitespace-nowrap"
        >
          <span className="text-xl">+</span>
          Nouvelle campagne
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {stats.map((stat, index) => (
          <div key={index} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
            <div className="flex items-start justify-between mb-4">
              <div className="p-2 bg-gray-50 rounded-lg">
                {stat.icon}
              </div>
              <span className={`text-xs font-semibold ${stat.changeColor}`}>{stat.change}</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 mb-1">{stat.value}</div>
            <div className="text-xs text-gray-600">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Search and Filters */}
      <div className="bg-white rounded-lg border border-gray-200 p-3 mb-6">
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <input
              type="text"
              placeholder="Rechercher une campagne..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-8 pl-9 pr-4 bg-white border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent"
            />
          </div>

          {/* Status Filter */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                className="h-8 border-dashed"
              >
                Statut
                {selectedStatuses.length > 0 && (
                  <>
                    <span className="ml-2 rounded-sm px-1 py-0.5 text-xs font-semibold bg-slate-100">
                      {selectedStatuses.length}
                    </span>
                  </>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[240px] p-2">
              <div className="flex items-center justify-between px-2 pb-2 border-b border-gray-100">
                <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest">Statut</span>
                {selectedStatuses.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setSelectedStatuses([])}
                    className="text-[11px] font-medium text-gray-500 hover:text-gray-800"
                  >
                    Effacer
                  </button>
                )}
              </div>
              <div className="grid gap-1 py-2">
                {statusOptions.map((option) => {
                  const isSelected = selectedStatuses.includes(option.value);
                  return (
                    <DropdownMenuItem
                      key={option.value}
                      onSelect={(event) => {
                        event.preventDefault();
                        toggleStatus(option.value);
                      }}
                      className={`flex items-center justify-between rounded-md px-2 py-2 cursor-pointer focus:bg-gray-50 ${
                        isSelected ? 'bg-gray-50 text-gray-900' : 'hover:bg-gray-50 text-gray-700'
                      }`}
                    >
                      <span className="inline-flex items-center gap-2 text-sm">
                        <span className={`h-2 w-2 rounded-full ${option.color.split(' ')[0]}`} />
                        {option.label}
                      </span>
                      <span className={`flex h-5 w-5 items-center justify-center rounded-full border ${isSelected ? 'border-slate-400 bg-slate-50' : 'border-gray-200'}`}>
                        {isSelected && <Check className="h-3 w-3 text-slate-700" />}
                      </span>
                    </DropdownMenuItem>
                  );
                })}
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Date Range Filters */}
          <Input
            type="date"
            value={dateMin}
            onChange={(e) => setDateMin(e.target.value)}
            max={dateMax || undefined}
            placeholder="Date début"
            className="h-8 w-[150px]"
          />
          <Input
            type="date"
            value={dateMax}
            onChange={(e) => setDateMax(e.target.value)}
            min={dateMin || undefined}
            placeholder="Date fin"
            className="h-8 w-[150px]"
          />

          {/* Reset Button */}
          {hasActiveFilters && (
            <Button
              variant="ghost"
              onClick={handleResetFilters}
              className="h-8 px-2 lg:px-3"
            >
              Réinitialiser
              <X className="ml-2 h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Campaigns Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {isLoading ? (
          <div className="col-span-full text-center py-12">
            <LoadingSpinner size="lg" />
            <p className="text-gray-500 mt-4">Chargement des campagnes...</p>
          </div>
        ) : displayedCampaigns.length === 0 ? (
          <div className="col-span-full text-center py-12">
            <p className="text-gray-500">Aucune campagne trouvée</p>
          </div>
        ) : (
          <>
            {displayedCampaigns.map((campaign) => (
            <div key={campaign.id} className={`bg-white rounded-xl shadow-sm border overflow-hidden hover:shadow-md transition-shadow ${
              campaign.status === 'Annulée'
                ? 'opacity-60 grayscale border-gray-200'
                : 'border-gray-100'
            }`}>
              {/* Campaign Header */}
              <div className="p-4 border-b border-gray-100">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-xs text-gray-500 mb-2">{campaign.code}</div>
                    <h3 className="text-lg font-bold text-gray-900">{campaign.title}</h3>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${campaign.statusColor}`}>
                        {campaign.status}
                      </span>
                      {campaign.isPreparing && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                          Préparation
                        </span>
                      )}
                      {campaign.type_campagne === 'avec_action_terrain' ? (
                        <>
                          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                            <MapPin className="w-3 h-3" />
                            Terrain
                          </span>
                          {campaign.visitMode && (
                            <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
                              {campaign.visitMode === 'TERRAIN' ? 'Sur place' : 'À distance'}
                            </span>
                          )}
                          {campaign.visitPurpose && (
                            <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200">
                              {campaign.visitPurpose === 'COMMERCIAL' ? 'Commercial' : 'Recouvrement'}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-slate-50 text-slate-600 border border-slate-200">
                          <Monitor className="w-3 h-3" />
                          Distance
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setOpenMenuId(openMenuId === campaign.id ? null : campaign.id)}
                      className="p-2 bg-white rounded-full hover:bg-gray-100 transition-colors cursor-pointer"
                    >
                      <MoreVertical className="w-4 h-4 text-gray-600" />
                    </button>
                    {openMenuId === campaign.id && (
                      <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-10">
                        {campaign.status === 'En cours' ? (
                          <button
                            type="button"
                            onClick={() => handlePauseCampaign(campaign.id)}
                            className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                          >
                            <Pause className="w-4 h-4" />
                            Désactiver
                          </button>
                        ) : campaign.status === 'En pause' ? (
                          <button
                            type="button"
                            onClick={() => void handleActivateCampaign(campaign.id, campaign.title)}
                            className="w-full px-4 py-2 text-left text-sm text-green-600 hover:bg-green-50 flex items-center gap-2"
                          >
                            <Play className="w-4 h-4" />
                            Activer
                          </button>
                        ) : null}
                        {campaign.status !== 'Annulée' && (
                          <button
                            type="button"
                            onClick={() => handleCancelCampaign(campaign.id, campaign.title)}
                            className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
                          >
                            <XCircle className="w-4 h-4" />
                            Annuler
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            setDuplicateCampaign(campaign);
                            setIsCreateModalOpen(true);
                            setOpenMenuId(null);
                          }}
                          className="w-full px-4 py-2 text-left text-sm text-blue-600 hover:bg-blue-50 flex items-center gap-2"
                        >
                          <Copy className="w-4 h-4" />
                          Dupliquer
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleOpenWorkflow(campaign)}
                  className="mt-4 inline-flex cursor-pointer items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-700"
                >
                  Voir le workflow
                </button>
              </div>

              {/* Campaign Details */}
              <div className="p-4">
                <p className="text-gray-600 text-sm mb-4 line-clamp-2">{campaign.description}</p>

                {/* Campaign Metrics */}
                <div className="mb-6">
                  {/* Progress Bar */}
                  <div className="mb-3">
                    <div className="flex justify-between items-center mb-1.5">
                      <span className="text-xs font-medium text-gray-600">Progression</span>
                      <span className="text-xs font-semibold text-gray-900">
                        {campaign.isPreparing
                          ? 'Préparation…'
                          : campaign.metrics.attribues > 0
                            ? `${Math.round((campaign.metrics.conversions / campaign.metrics.attribues) * 100)}%`
                            : '0%'}
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                      <div
                        className={`bg-gradient-to-r from-blue-500 to-blue-600 h-2 rounded-full transition-all duration-300 ${campaign.isPreparing ? 'animate-pulse' : ''}`}
                        style={{
                          width: campaign.isPreparing
                            ? '35%'
                            : campaign.metrics.attribues > 0
                              ? `${(campaign.metrics.conversions / campaign.metrics.attribues) * 100}%`
                              : '0%'
                        }}
                      />
                    </div>
                  </div>

                  {/* Metrics Grid */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                      <div className="flex-shrink-0 w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
                        <Target className="w-4 h-4 text-blue-600" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs text-gray-500 truncate">{campaign.isPreparing ? 'Population cible' : 'Attribués'}</div>
                        <div className="text-sm font-semibold text-gray-900">{campaign.isPreparing && !campaign.preparationCount ? '…' : campaign.metrics.attribues.toLocaleString('fr-FR')}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                      <div className="flex-shrink-0 w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center">
                        <Users className="w-4 h-4 text-purple-600" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs text-gray-500 truncate">Contactés</div>
                        <div className="text-sm font-semibold text-gray-900">{campaign.isPreparing ? '—' : campaign.metrics.contactes.toLocaleString('fr-FR')}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                      <div className="flex-shrink-0 w-8 h-8 bg-orange-100 rounded-lg flex items-center justify-center">
                        <TrendingUp className="w-4 h-4 text-orange-600" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs text-gray-500 truncate">En traitement</div>
                        <div className="text-sm font-semibold text-gray-900">{campaign.isPreparing ? '—' : campaign.metrics.enTraitement.toLocaleString('fr-FR')}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                      <div className="flex-shrink-0 w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center">
                        <Check className="w-4 h-4 text-green-600" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs text-gray-500 truncate">Conversions</div>
                        <div className="text-sm font-semibold text-gray-900">{campaign.isPreparing ? '—' : campaign.metrics.conversions.toLocaleString('fr-FR')}</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Debut</span>
                    <span className="font-medium text-gray-900">{campaign.startDate}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Fin</span>
                    <span className="font-medium text-gray-900">{campaign.endDate}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Cible</span>
                    <span className="font-medium text-gray-900">{campaign.target}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Modele</span>
                    <span className="font-medium text-gray-900">{campaign.model}</span>
                  </div>
                </div>
              </div>

            </div>
            ))}

            {/* Load More Trigger */}
            {hasNextPage && (
              <div ref={loadMoreRef} className="col-span-full py-8 flex justify-center">
                {isFetchingNextPage ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  <div className="text-sm text-gray-500">
                    {campaigns.length} campagne{campaigns.length > 1 ? 's' : ''} chargée{campaigns.length > 1 ? 's' : ''} sur {total}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
