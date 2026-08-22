import { useState, useEffect } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { campaignsApi } from '@/lib/api/definitions/campaigns.api';
import { getApiClient } from '@/lib/api/api-client';
import { invalidateCampaignCaches } from '@/lib/api/cache-invalidation';
import type { TypeCampagne, VisitMode, VisitPurpose } from '@/types/campaign.types';
import LoadingSpinner from '../LoadingSpinner';
import ConfirmDialog from '../ConfirmDialog';
import type { CibleCommercialPressureSummary } from '@/types/commercial-pressure.types';

const TYPE_CAMPAGNE_OPTIONS: ReadonlyArray<{ value: TypeCampagne; label: string; hint: string }> = [
  { value: 'sans_action_terrain', label: 'Sans action terrain', hint: 'CRC, DA, CC — traitement à distance' },
  { value: 'avec_action_terrain', label: 'Avec action terrain', hint: 'Agents sur le terrain' },
];

const VISIT_MODE_OPTIONS: ReadonlyArray<{ value: VisitMode; label: string; hint: string }> = [
  { value: 'TERRAIN', label: 'Terrain', hint: 'Visite physique sur place' },
  { value: 'A_DISTANCE', label: 'À distance', hint: 'Téléphone, visio' },
];

const VISIT_PURPOSE_OPTIONS: ReadonlyArray<{ value: VisitPurpose; label: string; hint: string }> = [
  { value: 'COMMERCIAL', label: 'Commercial', hint: 'Acquisition, vente' },
  { value: 'RECOUVREMENT', label: 'Recouvrement', hint: 'Recouvrement de créances' },
];

interface CampaignDuplicateData {
  nom_campagne: string;
  description: string;
  id_modele: string;
  id_cible: string;
  date_debut?: string;
  date_fin?: string;
  type_campagne?: TypeCampagne;
  visitMode?: VisitMode | null;
  visitPurpose?: VisitPurpose | null;
}

interface CreateCampaignModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  duplicateData?: CampaignDuplicateData;
}

interface ModeleAPIResponse {
  id_modele: string;
  nom_modele: string;
  date_creation?: string;
}

interface CibleAPIResponse {
  id_cible: string;
  nom_cible: string;
  source?: string;
  date_creation?: string;
}

interface CampaignCreateOptionsResponse {
  modeles: ModeleAPIResponse[];
  cibles: CibleAPIResponse[];
}

export default function CreateCampaignModal({ isOpen, onClose, onSuccess, duplicateData }: CreateCampaignModalProps) {
  const apiClient = getApiClient();
  const queryClient = useQueryClient();

  const [formData, setFormData] = useState<{
    nom_campagne: string;
    description: string;
    date_debut: string;
    date_fin: string;
    id_modele: string;
    id_cible: string;
    type_campagne: TypeCampagne;
    visitMode: VisitMode | '';
    visitPurpose: VisitPurpose | '';
  }>({
    nom_campagne: '',
    description: '',
    date_debut: '',
    date_fin: '',
    id_modele: '',
    id_cible: '',
    type_campagne: 'sans_action_terrain',
    visitMode: '',
    visitPurpose: '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pressureConfirmOpen, setPressureConfirmOpen] = useState(false);
  const [pressureWarning, setPressureWarning] = useState<CibleCommercialPressureSummary | null>(null);

  // Une seule requête légère pour les deux sélecteurs de la modale.
  const { data: createOptions, isLoading: createOptionsLoading } = useQuery<CampaignCreateOptionsResponse>({
    queryKey: ['campaign-meta', 'create-options'],
    queryFn: () => apiClient.request<CampaignCreateOptionsResponse>(campaignsApi.createOptions()),
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  const modeles = createOptions?.modeles ?? [];
  const cibles = createOptions?.cibles ?? [];
  const modelesLoading = createOptionsLoading;
  const ciblesLoading = createOptionsLoading;


  const pressurePreviewQuery = useQuery<CibleCommercialPressureSummary>({
    queryKey: ['campaign-pressure-preview', formData.id_cible],
    queryFn: () => apiClient.request<CibleCommercialPressureSummary>(campaignsApi.pressurePreview(formData.id_cible)),
    enabled: false,
    staleTime: 30 * 1000,
    retry: 1,
  });

  // Le backend renvoie déjà les options de la plus récente à la plus ancienne.
  useEffect(() => {
    if (modeles.length > 0 && !formData.id_modele) {
      setFormData((prev) => ({ ...prev, id_modele: modeles[0].id_modele }));
    }
  }, [modeles, formData.id_modele]);

  useEffect(() => {
    if (cibles.length > 0 && !formData.id_cible) {
      setFormData((prev) => ({ ...prev, id_cible: cibles[0].id_cible }));
    }
  }, [cibles, formData.id_cible]);

  // Pre-fill form when duplicating
  useEffect(() => {
    if (duplicateData && isOpen) {
      setFormData({
        nom_campagne: `${duplicateData.nom_campagne} (copie)`,
        description: duplicateData.description || '',
        date_debut: duplicateData.date_debut || '',
        date_fin: duplicateData.date_fin || '',
        id_modele: duplicateData.id_modele,
        id_cible: duplicateData.id_cible,
        type_campagne: duplicateData.type_campagne || 'sans_action_terrain',
        visitMode: duplicateData.visitMode || '',
        visitPurpose: duplicateData.visitPurpose || '',
      });
    }
  }, [duplicateData, isOpen]);

  // Create campaign mutation
  const createMutation = useMutation({
    mutationFn: (data: typeof formData) => {
      const isTerrain = data.type_campagne === 'avec_action_terrain';
      return apiClient.request(
        campaignsApi.create({
          nom_campagne: data.nom_campagne,
          id_modele: data.id_modele,
          id_cible: data.id_cible,
          date_debut: data.date_debut,
          date_fin: data.date_fin,
          description: data.description,
          type_campagne: data.type_campagne,
          visitMode: isTerrain ? (data.visitMode || null) : null,
          visitPurpose: isTerrain ? (data.visitPurpose || null) : null,
        })
      );
    },
    onSuccess: () => {
      void invalidateCampaignCaches(queryClient);
      onSuccess?.();
      onClose();
      resetForm();
    },
    onError: (error: any) => {
      console.error('Error creating campaign:', error);
      setErrors({ submit: 'Une erreur est survenue lors de la création de la campagne' });
    },
  });

  const resetForm = () => {
    setFormData({
      nom_campagne: '',
      description: '',
      date_debut: '',
      date_fin: '',
      id_modele: '',
      id_cible: '',
      type_campagne: 'sans_action_terrain',
      visitMode: '',
      visitPurpose: '',
    });
    setErrors({});
    setPressureConfirmOpen(false);
    setPressureWarning(null);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    const newErrors: Record<string, string> = {};

    if (!formData.nom_campagne.trim()) {
      newErrors.nom_campagne = 'Le nom est requis';
    }
    if (!formData.description.trim()) {
      newErrors.description = 'La description est requise';
    }
    if (!formData.date_debut) {
      newErrors.date_debut = 'La date de début est requise';
    }
    if (!formData.date_fin) {
      newErrors.date_fin = 'La date de fin est requise';
    }
    if (formData.date_debut && formData.date_fin && formData.date_debut > formData.date_fin) {
      newErrors.date_fin = 'La date de fin doit être après la date de début';
    }
    if (!formData.id_modele) {
      newErrors.id_modele = 'Le modèle est requis';
    }
    if (!formData.id_cible) {
      newErrors.id_cible = 'La cible est requise';
    }
    if (formData.type_campagne === 'avec_action_terrain') {
      if (!formData.visitMode) {
        newErrors.visitMode = 'Le mode de visite est requis';
      }
      if (!formData.visitPurpose) {
        newErrors.visitPurpose = 'L\'objet de la visite est requis';
      }
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    void (async () => {
      try {
        const refreshed = await pressurePreviewQuery.refetch();
        if (refreshed.error) throw refreshed.error;
        const pressure = refreshed.data;
        if (pressure?.supported && pressure.warning) {
          setPressureWarning(pressure);
          setPressureConfirmOpen(true);
          return;
        }
        createMutation.mutate(formData);
      } catch (error) {
        console.error('Error checking commercial pressure:', error);
        setErrors((prev) => ({ ...prev, submit: 'Impossible de vérifier la pression commerciale de la cible.' }));
      }
    })();
  };

  const handleEscape = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && isOpen && !pressureConfirmOpen) {
      handleClose();
    }
  };

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen, pressureConfirmOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={handleClose}
    >
      <div
        className="relative bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 sticky top-0 bg-white z-10">
          <h2 className="text-lg font-bold text-gray-900">{duplicateData ? 'Dupliquer la Campagne' : 'Nouvelle Campagne'}</h2>
          <button
            onClick={handleClose}
            className="p-1.5 hover:bg-gray-100 rounded-full transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5 text-gray-600" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Campaign Name & Description Row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="nom_campagne" className="block text-xs font-medium text-gray-700 mb-1.5">
                Nom de la campagne <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                id="nom_campagne"
                value={formData.nom_campagne}
                onChange={(e) => {
                  setFormData({ ...formData, nom_campagne: e.target.value });
                  setErrors({ ...errors, nom_campagne: '' });
                }}
                className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 ${
                  errors.nom_campagne ? 'border-red-500' : 'border-gray-300'
                }`}
                placeholder="Ex: Campagne Printemps 2026"
              />
              {errors.nom_campagne && (
                <p className="mt-1 text-xs text-red-500">{errors.nom_campagne}</p>
              )}
            </div>

            <div>
              <label htmlFor="description" className="block text-xs font-medium text-gray-700 mb-1.5">
                Description <span className="text-red-500">*</span>
              </label>
              <textarea
                id="description"
                value={formData.description}
                onChange={(e) => {
                  setFormData({ ...formData, description: e.target.value });
                  setErrors({ ...errors, description: '' });
                }}
                className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 ${
                  errors.description ? 'border-red-500' : 'border-gray-300'
                }`}
                placeholder="Décrivez votre campagne"
                rows={2}
              />
              {errors.description && (
                <p className="mt-1 text-xs text-red-500">{errors.description}</p>
              )}
            </div>
          </div>

          {/* Date Range */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label htmlFor="date_debut" className="block text-xs font-medium text-gray-700 mb-1.5">
                Date de début <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                id="date_debut"
                value={formData.date_debut}
                onChange={(e) => {
                  setFormData({ ...formData, date_debut: e.target.value });
                  setErrors({ ...errors, date_debut: '' });
                }}
                className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 ${
                  errors.date_debut ? 'border-red-500' : 'border-gray-300'
                }`}
              />
              {errors.date_debut && (
                <p className="mt-1 text-xs text-red-500">{errors.date_debut}</p>
              )}
            </div>

            <div>
              <label htmlFor="date_fin" className="block text-xs font-medium text-gray-700 mb-1.5">
                Date de fin <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                id="date_fin"
                value={formData.date_fin}
                onChange={(e) => {
                  setFormData({ ...formData, date_fin: e.target.value });
                  setErrors({ ...errors, date_fin: '' });
                }}
                className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 ${
                  errors.date_fin ? 'border-red-500' : 'border-gray-300'
                }`}
              />
              {errors.date_fin && (
                <p className="mt-1 text-xs text-red-500">{errors.date_fin}</p>
              )}
            </div>

            {/* Model Select */}
            <div>
              <label htmlFor="id_modele" className="block text-xs font-medium text-gray-700 mb-1.5">
                Modèle <span className="text-red-500">*</span>
              </label>
              {modelesLoading ? (
                <div className="flex items-center justify-center py-2">
                  <LoadingSpinner size="sm" />
                </div>
              ) : (
                <select
                  id="id_modele"
                  value={formData.id_modele}
                  onChange={(e) => {
                    setFormData({ ...formData, id_modele: e.target.value });
                    setErrors({ ...errors, id_modele: '' });
                  }}
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 ${
                    errors.id_modele ? 'border-red-500' : 'border-gray-300'
                  }`}
                >
                  <option value="">Sélectionner un modèle</option>
                  {modeles.map((modele) => (
                    <option key={modele.id_modele} value={modele.id_modele}>
                      {modele.nom_modele}
                    </option>
                  ))}
                </select>
              )}
              {errors.id_modele && (
                <p className="mt-1 text-xs text-red-500">{errors.id_modele}</p>
              )}
            </div>

            {/* Cible Select */}
            <div>
              <label htmlFor="id_cible" className="block text-xs font-medium text-gray-700 mb-1.5">
                Cible <span className="text-red-500">*</span>
              </label>
              {ciblesLoading ? (
                <div className="flex items-center justify-center py-2">
                  <LoadingSpinner size="sm" />
                </div>
              ) : (
                <select
                  id="id_cible"
                  value={formData.id_cible}
                  onChange={(e) => {
                    setFormData({ ...formData, id_cible: e.target.value });
                    setErrors({ ...errors, id_cible: '' });
                  }}
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 ${
                    errors.id_cible ? 'border-red-500' : 'border-gray-300'
                  }`}
                >
                  <option value="">Sélectionner une cible</option>
                  {cibles.map((cible) => (
                    <option key={cible.id_cible} value={cible.id_cible}>
                      {cible.nom_cible}{cible.source ? ` (${cible.source})` : ''}
                    </option>
                  ))}
                </select>
              )}
              {errors.id_cible && (
                <p className="mt-1 text-xs text-red-500">{errors.id_cible}</p>
              )}
            </div>
          </div>

          {pressurePreviewQuery.data?.supported && pressurePreviewQuery.data.warning && (
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="text-sm font-semibold">Pression commerciale élevée dans cette cible</p>
                <p className="mt-1 text-xs">
                  {pressurePreviewQuery.data.pct_eleve.toFixed(1)} % des clients éligibles sont actuellement en pression élevée.
                  Une confirmation sera demandée avant la création si ce taux reste supérieur à {pressurePreviewQuery.data.warning_threshold_pct.toFixed(0)} %.
                </p>
              </div>
            </div>
          )}

          {/* Campaign Type */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1.5">
              Type de campagne <span className="text-red-500">*</span>
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {TYPE_CAMPAGNE_OPTIONS.map((option) => {
                const selected = formData.type_campagne === option.value;
                return (
                  <label
                    key={option.value}
                    className={`flex items-start gap-3 px-3 py-2 border rounded-lg cursor-pointer transition-colors ${
                      selected ? 'border-slate-900 bg-slate-50' : 'border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="type_campagne"
                      value={option.value}
                      checked={selected}
                      onChange={() => setFormData({ ...formData, type_campagne: option.value })}
                      className="mt-1"
                    />
                    <div>
                      <div className="text-sm font-medium text-gray-900">{option.label}</div>
                      <div className="text-xs text-gray-500">{option.hint}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Visit Mode & Purpose (terrain only) */}
          {formData.type_campagne === 'avec_action_terrain' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">
                  Mode de visite <span className="text-red-500">*</span>
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {VISIT_MODE_OPTIONS.map((option) => {
                    const selected = formData.visitMode === option.value;
                    return (
                      <label
                        key={option.value}
                        className={`flex items-start gap-2 px-3 py-2 border rounded-lg cursor-pointer transition-colors ${
                          selected ? 'border-slate-900 bg-slate-50' : 'border-gray-300 hover:bg-gray-50'
                        }`}
                      >
                        <input
                          type="radio"
                          name="visitMode"
                          value={option.value}
                          checked={selected}
                          onChange={() => {
                            setFormData({ ...formData, visitMode: option.value });
                            setErrors({ ...errors, visitMode: '' });
                          }}
                          className="mt-1"
                        />
                        <div>
                          <div className="text-sm font-medium text-gray-900">{option.label}</div>
                          <div className="text-xs text-gray-500">{option.hint}</div>
                        </div>
                      </label>
                    );
                  })}
                </div>
                {errors.visitMode && (
                  <p className="mt-1 text-xs text-red-500">{errors.visitMode}</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">
                  Objet de la visite <span className="text-red-500">*</span>
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {VISIT_PURPOSE_OPTIONS.map((option) => {
                    const selected = formData.visitPurpose === option.value;
                    return (
                      <label
                        key={option.value}
                        className={`flex items-start gap-2 px-3 py-2 border rounded-lg cursor-pointer transition-colors ${
                          selected ? 'border-slate-900 bg-slate-50' : 'border-gray-300 hover:bg-gray-50'
                        }`}
                      >
                        <input
                          type="radio"
                          name="visitPurpose"
                          value={option.value}
                          checked={selected}
                          onChange={() => {
                            setFormData({ ...formData, visitPurpose: option.value });
                            setErrors({ ...errors, visitPurpose: '' });
                          }}
                          className="mt-1"
                        />
                        <div>
                          <div className="text-sm font-medium text-gray-900">{option.label}</div>
                          <div className="text-xs text-gray-500">{option.hint}</div>
                        </div>
                      </label>
                    );
                  })}
                </div>
                {errors.visitPurpose && (
                  <p className="mt-1 text-xs text-red-500">{errors.visitPurpose}</p>
                )}
              </div>
            </div>
          )}

          {/* Submit Error */}
          {errors.submit && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-xs text-red-600">{errors.submit}</p>
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-200 sticky bottom-0 bg-white">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors font-medium text-sm"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || pressurePreviewQuery.isFetching}
              className="px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {(createMutation.isPending || pressurePreviewQuery.isFetching) && <LoadingSpinner size="sm" />}
              {createMutation.isPending
                ? 'Création...'
                : pressurePreviewQuery.isFetching
                  ? 'Vérification...'
                  : (duplicateData ? 'Dupliquer' : 'Créer la campagne')}
            </button>
          </div>
        </form>
      </div>

      <div onClick={(e) => e.stopPropagation()}>
        <ConfirmDialog
          isOpen={pressureConfirmOpen}
          onClose={() => setPressureConfirmOpen(false)}
          onConfirm={() => createMutation.mutate(formData)}
          title="Confirmer la campagne"
          message={pressureWarning
            ? `${pressureWarning.pct_eleve.toFixed(1)} % des clients de cette campagne sont en pression commerciale élevée. Êtes-vous certain de vouloir poursuivre ?`
            : 'Cette campagne contient une part importante de clients en pression commerciale élevée. Êtes-vous certain de vouloir poursuivre ?'}
          confirmText="Créer quand même"
          cancelText="Revoir la campagne"
          type="warning"
        />
      </div>
    </div>
  );
}
