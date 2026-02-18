import { Mail, Phone, Users, MessageSquare, RefreshCw } from 'lucide-react';
import { useMemo, useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queuesApi } from '@/lib/api/definitions/queues.api';
import { batchApi } from '@/lib/api/definitions/batch.api';
import { getApiClient } from '@/lib/api/api-client';
import type { QueueContact } from '@/types/campaign.types';
import Toast from '../../components/Toast';
import LoadingSpinner from '../../components/LoadingSpinner';
import { Button } from '@/components/ui/button';
import CampaignSelect from '@/components/custom/CampaignSelect';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

type QueueType = 'crc' | 'da' | 'cc';

const normalizeKey = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, '');

const formatKeyLabel = (key: string) => {
  const withSpaces = key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();
  return withSpaces;
};

const getKeyRank = (key: string) => {
  const normalized = normalizeKey(key);

  if (normalized.includes('prenom') || normalized.includes('firstname')) return 0;
  if (normalized.includes('nom') || normalized.includes('lastname') || normalized.includes('name')) return 1;
  if (normalized.includes('telephone') || normalized.includes('tel') || normalized.includes('mobile') || normalized.includes('gsm')) return 2;
  if (normalized.includes('email') || normalized.includes('mail')) return 3;
  if (normalized.includes('idcampagne')) return 4;
  if (normalized.includes('radicalcompte') || normalized.includes('radical')) return 5;
  if (normalized.startsWith('id')) return 6;

  return 10;
};

export default function CRCPage() {
  const apiClient = getApiClient();
  const queryClient = useQueryClient();
  const [selectedQueue, setSelectedQueue] = useState<QueueType | null>(null);
  const [selectedCampaign, setSelectedCampaign] = useState<string | null>(null);
  const [selectedGestionnaire, setSelectedGestionnaire] = useState<string | null>(null);
  const [previousContact, setPreviousContact] = useState<QueueContact | null>(null);
  const [showPrevious, setShowPrevious] = useState(false);
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' | 'warning' }>({
    isOpen: false,
    title: '',
  });

  // Fetch gestionnaires list
  const { data: gestionnairesData } = useQuery<{ gestionnaires: string[] }>({
    queryKey: ['gestionnaires'],
    queryFn: () => apiClient.request<{ gestionnaires: string[] }>(queuesApi.getGestionnaires()),
  });

  // Fetch next contact from selected queue
  const {
    data: contact,
    isLoading,
    error,
  } = useQuery<QueueContact | null>({
    queryKey: ['queue-next', selectedQueue, selectedCampaign, selectedGestionnaire],
    queryFn: () => selectedQueue ? apiClient.request<QueueContact>(queuesApi.getNext(selectedQueue, selectedCampaign, selectedGestionnaire)) : null,
    enabled: !!selectedQueue,
    retry: false,
  });

  useEffect(() => {
    setPreviousContact(null);
    setShowPrevious(false);
  }, [selectedQueue, selectedCampaign, selectedGestionnaire]);

  const displayContact = showPrevious && previousContact ? previousContact : contact;

  // Apply result mutation
  const applyResultMutation = useMutation({
    mutationFn: (data: { resultat: string }) => {
      // Extract id_campagne and radical_compte from row object
      const idCampagne = displayContact?.row?.ID_CAMPAGNE || displayContact?.row?.id_campagne;
      const radicalCompte = displayContact?.row?.Radical_compte || displayContact?.row?.radical_compte;

      if (!idCampagne || !radicalCompte) {
        throw new Error('Informations du contact manquantes (ID_CAMPAGNE ou Radical_compte)');
      }
      return apiClient.request(
        queuesApi.applyResult(selectedQueue!, {
          id_campagne: idCampagne,
          radical_compte: radicalCompte,
          resultat: data.resultat,
        })
      );
    },
    onSuccess: () => {
      setShowPrevious(false);
      queryClient.invalidateQueries({ queryKey: ['queue-next', selectedQueue, selectedCampaign] });
      setToast({
        isOpen: true,
        title: 'Succes',
        message: 'Resultat applique avec succes',
        type: 'success',
      });
    },
    onError: (error: any) => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: error?.message || 'Impossible d\'appliquer le resultat',
        type: 'error',
      });
    },
  });

  // Skip mutation
  const skipMutation = useMutation({
    mutationFn: () => {
      // Extract id_campagne and radical_compte from row object
      const idCampagne = displayContact?.row?.ID_CAMPAGNE || displayContact?.row?.id_campagne;
      const radicalCompte = displayContact?.row?.Radical_compte || displayContact?.row?.radical_compte;

      if (!idCampagne || !radicalCompte) {
        throw new Error('Informations du contact manquantes (ID_CAMPAGNE ou Radical_compte)');
      }
      return apiClient.request(
        queuesApi.skip(selectedQueue!, {
          id_campagne: idCampagne,
          radical_compte: radicalCompte,
        })
      );
    },
    onSuccess: () => {
      setShowPrevious(false);
      queryClient.invalidateQueries({ queryKey: ['queue-next', selectedQueue, selectedCampaign] });
      setToast({
        isOpen: true,
        title: 'Succes',
        message: 'Contact passe',
        type: 'success',
      });
    },
    onError: (error: any) => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: error?.message || 'Impossible de passer le contact',
        type: 'error',
      });
    },
  });

  const runBatchMutation = useMutation({
    mutationFn: () => apiClient.request(batchApi.run()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue-next', selectedQueue, selectedCampaign] });
      setToast({
        isOpen: true,
        title: 'Succes',
        message: 'Batch lance avec succes',
        type: 'success',
      });
    },
    onError: (error: any) => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: error?.message || 'Impossible de lancer le batch',
        type: 'error',
      });
    },
  });

  // Initiate call mutation (CRC only)
  const callMutation = useMutation({
    mutationFn: () => apiClient.request(queuesApi.initiateCall()),
    onSuccess: () => {
      setToast({
        isOpen: true,
        title: 'Succes',
        message: 'Appel initie',
        type: 'success',
      });
    },
    onError: () => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Impossible d\'initier l\'appel',
        type: 'error',
      });
    },
  });

  const handleApplyResult = (resultat: string) => {
    if (!showPrevious && contact) {
      setPreviousContact(contact);
    }

    const idCampagne = displayContact?.row?.ID_CAMPAGNE || displayContact?.row?.id_campagne;
    const radicalCompte = displayContact?.row?.Radical_compte || displayContact?.row?.radical_compte;

    if (!idCampagne || !radicalCompte) {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Impossible d\'appliquer le resultat: informations manquantes',
        type: 'error',
      });
      return;
    }
    applyResultMutation.mutate({ resultat });
  };

  const handleSkip = () => {
    if (!showPrevious && contact) {
      setPreviousContact(contact);
    }

    const idCampagne = displayContact?.row?.ID_CAMPAGNE || displayContact?.row?.id_campagne;
    const radicalCompte = displayContact?.row?.Radical_compte || displayContact?.row?.radical_compte;

    if (!idCampagne || !radicalCompte) {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Impossible de passer: informations manquantes',
        type: 'error',
      });
      return;
    }
    skipMutation.mutate();
  };

  const handleCall = () => {
    callMutation.mutate();
  };

  const queueBlocks = [
    {
      id: 'crc' as QueueType,
      title: 'CRC',
      subtitle: 'Contact Relance Client',
      icon: Phone,
      bgColor: 'bg-pink-50',
      borderColor: 'border-pink-200',
      iconColor: 'text-pink-600',
      iconBg: 'bg-pink-100',
    },
    {
      id: 'da' as QueueType,
      title: 'DA',
      subtitle: 'Detection Anomalies',
      icon: Users,
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-200',
      iconColor: 'text-blue-600',
      iconBg: 'bg-blue-100',
    },
    {
      id: 'cc' as QueueType,
      title: 'CC',
      subtitle: 'Contact Client',
      icon: MessageSquare,
      bgColor: 'bg-green-50',
      borderColor: 'border-green-200',
      iconColor: 'text-green-600',
      iconBg: 'bg-green-100',
    },
  ];

  const selectedQueueBlock = queueBlocks.find((block) => block.id === selectedQueue);
  const selectedQueueDotColor = selectedQueueBlock?.iconColor
    ? selectedQueueBlock.iconColor.replace('text-', 'bg-')
    : 'bg-gray-300';

  const rowEntries = useMemo(() => {
    if (!displayContact?.row) return [];
    return Object.entries(displayContact.row);
  }, [displayContact]);

  const sortedEntries = useMemo(() => {
    if (rowEntries.length === 0) return [];
    return [...rowEntries].sort((a, b) => {
      const rankDiff = getKeyRank(a[0]) - getKeyRank(b[0]);
      if (rankDiff !== 0) return rankDiff;
      return a[0].localeCompare(b[0]);
    });
  }, [rowEntries]);

  const primaryEntries = sortedEntries.slice(0, 6);
  const secondaryEntries = sortedEntries.slice(6);

  const contextEntries = useMemo(() => {
    if (!displayContact?.context) return [];
    return Object.entries(displayContact.context);
  }, [displayContact]);

  const contactSummary = useMemo(() => {
    const findValue = (predicate: (normalized: string) => boolean) => {
      const entry = rowEntries.find(([key]) => predicate(normalizeKey(key)));
      if (!entry) return undefined;
      const value = entry[1];
      return value !== null && value !== undefined ? String(value) : undefined;
    };

    const firstName = findValue(key => key.includes('prenom') || key.includes('firstname'));
    const lastName = findValue(key => key.includes('nom') || key.includes('lastname'));
    const phone = findValue(key => key.includes('telephone') || key.includes('tel') || key.includes('mobile') || key.includes('gsm'));
    const email = findValue(key => key.includes('email') || key.includes('mail'));
    const campaignId = findValue(key => key.includes('idcampagne'));
    const accountId = findValue(key => key.includes('radicalcompte') || key.includes('radical'));

    const nameParts = [firstName, lastName].filter(Boolean);
    const name = nameParts.length > 0 ? nameParts.join(' ') : undefined;

    return {
      name,
      phone,
      email,
      campaignId,
      accountId,
    };
  }, [rowEntries]);

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8 max-w-full overflow-x-hidden">
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />

      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6 sm:mb-8">
        <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-2">Contact Client</h1>
        <p className="text-gray-600">Selectionnez une file d'attente pour traiter les contacts</p>
      </div>

      {/* Queue Selection Blocks */}
      {!selectedQueue && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6">
          {queueBlocks.map((block) => {
            const Icon = block.icon;
            return (
              <button
                key={block.id}
                onClick={() => setSelectedQueue(block.id)}
                className={`${block.bgColor} border-2 ${block.borderColor} rounded-2xl p-4 hover:shadow-lg transition-all cursor-pointer text-left group`}
              >
                <div className={`${block.iconBg} p-3 rounded-xl inline-flex mb-4`}>
                  <Icon className={`w-6 h-6 ${block.iconColor}`} />
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-1">{block.title}</h2>
                <p className="text-sm text-gray-600">{block.subtitle}</p>
                <div className="mt-4 text-sm font-medium text-gray-700 group-hover:text-gray-900">
                  Cliquez pour commencer
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Selected Queue Processing */}
      {selectedQueue && (
        <div className="space-y-6">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div className={`${selectedQueueBlock?.bgColor ?? 'bg-white'} border-2 ${selectedQueueBlock?.borderColor ?? 'border-gray-200'} rounded-xl p-4 sm:p-5 w-full`}>
              <div className="flex items-center gap-3">
                <div className={`${selectedQueueBlock?.iconBg ?? 'bg-gray-100'} p-2 rounded-lg`}>
                  {selectedQueueBlock?.icon && (
                    <selectedQueueBlock.icon className={`w-5 h-5 ${selectedQueueBlock.iconColor}`} />
                  )}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-900">{selectedQueueBlock?.title}</h2>
                  <p className="text-sm text-gray-600">{selectedQueueBlock?.subtitle}</p>
                </div>
              </div>
            </div>
            <div className="w-full lg:w-auto flex flex-col gap-2">
              <Button
                variant="outline"
                onClick={() => setSelectedQueue(null)}
                className="w-full lg:w-auto"
              >
                Retour a la selection
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowPrevious((prev) => !prev)}
                disabled={!previousContact}
                className="w-full lg:w-auto"
              >
                {showPrevious ? 'Retour au contact courant' : 'Voir le contact precedent'}
              </Button>
              <Button
                onClick={() => runBatchMutation.mutate()}
                disabled={runBatchMutation.isPending}
                className="w-full lg:w-auto"
              >
                {runBatchMutation.isPending ? (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                    Rafraichir...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Rafraichir
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Filters */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 flex-1">
                <label className="text-sm font-semibold text-gray-900 whitespace-nowrap">
                  Campagne:
                </label>
                <CampaignSelect
                  value={selectedCampaign}
                  onValueChange={setSelectedCampaign}
                  className="w-full sm:w-64"
                />
              </div>
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 flex-1">
                <label className="text-sm font-semibold text-gray-900 whitespace-nowrap">
                  Gestionnaire:
                </label>
                <Select
                  value={selectedGestionnaire ?? "all"}
                  onValueChange={(value) => setSelectedGestionnaire(value === "all" ? null : value)}
                >
                  <SelectTrigger className="w-full sm:w-64">
                    <SelectValue placeholder="Tous les gestionnaires" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Tous les gestionnaires</SelectItem>
                    {gestionnairesData?.gestionnaires.map((gestionnaire) => (
                      <SelectItem key={gestionnaire} value={gestionnaire}>
                        {gestionnaire}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="flex items-center justify-center py-20">
              <LoadingSpinner size="lg" />
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="bg-red-50 border-l-4 border-red-500 rounded p-4">
              <p className="text-sm text-red-900">
                Erreur lors du chargement du contact: {error.message}
              </p>
            </div>
          )}

          {/* Empty State */}
          {!isLoading && !error && (!displayContact || !displayContact.row) && (
            <div className="bg-blue-50 border-l-4 border-blue-500 rounded p-4">
              <p className="text-sm text-blue-900">Aucune ligne a traiter.</p>
            </div>
          )}

          {/* Contact Card */}
          {!isLoading && !error && displayContact && displayContact.row && (
            <div className="grid grid-cols-1 xl:grid-cols-[2fr_1fr] gap-6">
              <div className="space-y-6">
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
                  <div className="flex flex-col gap-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <div className={`w-2.5 h-2.5 ${selectedQueueDotColor} rounded-full`}></div>
                          <h2 className="text-lg sm:text-xl font-bold text-gray-900">
                            {showPrevious ? 'Contact precedent' : 'Contact a traiter'}
                          </h2>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          {rowEntries.length} champ{rowEntries.length > 1 ? 's' : ''} dans le dossier
                        </p>
                      </div>
                      <div className="text-xs text-gray-500">File {selectedQueueBlock?.title}</div>
                    </div>

                    {(contactSummary.name || contactSummary.phone || contactSummary.email || contactSummary.campaignId || contactSummary.accountId) && (
                      <div className="rounded-xl border border-gray-100 bg-slate-50 p-3">
                        {contactSummary.name && (
                          <div className="text-sm font-semibold text-gray-900 mb-2">
                            {contactSummary.name}
                          </div>
                        )}
                        <div className="flex flex-wrap gap-2">
                          {contactSummary.phone && (
                            <a
                              href={`tel:${contactSummary.phone}`}
                              className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                            >
                              <Phone className="h-3.5 w-3.5 text-gray-500" />
                              {contactSummary.phone}
                            </a>
                          )}
                          {contactSummary.email && (
                            <a
                              href={`mailto:${contactSummary.email}`}
                              className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                            >
                              <Mail className="h-3.5 w-3.5 text-gray-500" />
                              {contactSummary.email}
                            </a>
                          )}
                          {contactSummary.campaignId && (
                            <span className="inline-flex items-center rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                              Campagne {contactSummary.campaignId}
                            </span>
                          )}
                          {contactSummary.accountId && (
                            <span className="inline-flex items-center rounded-full border border-amber-100 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                              Compte {contactSummary.accountId}
                            </span>
                          )}
                          {displayContact.flags?.arriv_eche === true && (
                            <span className="inline-flex items-center rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-medium text-red-700">
                              🚨 Echeance proche
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="mt-6">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-gray-900">Informations essentielles</h3>
                      <span className="text-xs text-gray-500">Essentiel</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {primaryEntries.map(([key, value]) => (
                        <div key={key} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                          <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                            {formatKeyLabel(key)}
                          </div>
                          <div className="text-sm font-semibold text-gray-900 break-words">
                            {value !== null && value !== undefined ? String(value) : '-'}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-gray-900">Details complementaires</h3>
                    <span className="text-xs text-gray-500">
                      {secondaryEntries.length + contextEntries.length} champs
                    </span>
                  </div>
                  {secondaryEntries.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
                      {secondaryEntries.map(([key, value]) => (
                        <div key={key} className="flex items-start gap-3">
                          <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide min-w-[140px]">
                            {formatKeyLabel(key)}
                          </span>
                          <span className="text-sm text-gray-900 break-words">
                            {value !== null && value !== undefined ? String(value) : '-'}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">Aucun champ supplementaire.</p>
                  )}

                  {contextEntries.length > 0 && (
                    <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-sm font-semibold text-gray-900">Contexte</h4>
                        <span className="text-xs text-gray-500">
                          {contextEntries.length} champ{contextEntries.length > 1 ? 's' : ''}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                        {contextEntries.map(([key, value]) => (
                          <div key={key} className="flex items-start gap-2">
                            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                              {formatKeyLabel(key)}
                            </span>
                            <span className="text-sm font-medium text-gray-900 break-words">
                              {value !== null && value !== undefined ? String(value) : '-'}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="space-y-6 xl:sticky xl:top-24 h-fit">
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
                  <h3 className="text-sm font-semibold text-gray-900 mb-4">Actions rapides</h3>
                  <div className="flex flex-col gap-3">
                    {selectedQueue === 'crc' && (
                      <Button
                        onClick={handleCall}
                        disabled={callMutation.isPending}
                        className="bg-slate-900 text-white hover:bg-slate-800"
                      >
                        <Phone className="w-4 h-4 mr-2" />
                        {callMutation.isPending ? 'Appel en cours...' : 'Appeler'}
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      onClick={handleSkip}
                      disabled={
                        skipMutation.isPending ||
                        !(displayContact.row?.ID_CAMPAGNE || displayContact.row?.id_campagne) ||
                        !(displayContact.row?.Radical_compte || displayContact.row?.radical_compte)
                      }
                    >
                      {skipMutation.isPending ? 'Passage en cours...' : 'Passer'}
                    </Button>
                  </div>
                </div>

                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-gray-900">Resultats</h3>
                    <span className="text-xs text-gray-500">{displayContact.resultats?.length || 0}</span>
                  </div>
                  {displayContact.resultats && displayContact.resultats.length > 0 ? (
                    <div className="flex flex-col gap-2">
                      {displayContact.resultats.map((resultat) => (
                        <Button
                          key={resultat}
                          variant="outline"
                          onClick={() => handleApplyResult(resultat)}
                          disabled={
                            applyResultMutation.isPending ||
                            !(displayContact.row?.ID_CAMPAGNE || displayContact.row?.id_campagne) ||
                            !(displayContact.row?.Radical_compte || displayContact.row?.radical_compte)
                          }
                          className="w-full justify-center hover:bg-slate-900 hover:text-white transition-colors text-sm"
                        >
                          {resultat}
                        </Button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">Aucun resultat disponible.</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );
}


