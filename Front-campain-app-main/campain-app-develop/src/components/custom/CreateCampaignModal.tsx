import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { ciblesApi } from '@/lib/api/definitions/cibles.api';
import { campaignsApi } from '@/lib/api/definitions/campaigns.api';
import { getApiClient } from '@/lib/api/api-client';
import LoadingSpinner from '../LoadingSpinner';

interface CampaignDuplicateData {
  nom_campagne: string;
  description: string;
  id_modele: string;
  id_cible: string;
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
  date_creation: string;
}

interface CibleAPIResponse {
  id: string;
  id_cible?: string;
  nom_cible: string;
  source: string;
  created_at?: string;
  date_creation?: string;
}

export default function CreateCampaignModal({ isOpen, onClose, onSuccess, duplicateData }: CreateCampaignModalProps) {
  const apiClient = getApiClient();
  const queryClient = useQueryClient();

  const [formData, setFormData] = useState({
    nom_campagne: '',
    description: '',
    date_debut: '',
    date_fin: '',
    id_modele: '',
    id_cible: '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  // Fetch modeles (API returns paginated response with items array)
  const { data: modeles = [], isLoading: modelesLoading } = useQuery({
    queryKey: ['modeles'],
    queryFn: async () => {
      const response = await apiClient.request<{ items: ModeleAPIResponse[] } | ModeleAPIResponse[]>(
        modelesApi.findAll()
      );
      return Array.isArray(response) ? response : response?.items ?? [];
    },
    enabled: isOpen,
  });

  // Fetch cibles (API returns direct array)
  const { data: cibles = [], isLoading: ciblesLoading } = useQuery({
    queryKey: ['cibles'],
    queryFn: async () => {
      const response = await apiClient.request<CibleAPIResponse[] | { items: CibleAPIResponse[] }>(
        ciblesApi.findAll()
      );
      return Array.isArray(response) ? response : response?.items ?? [];
    },
    enabled: isOpen,
  });

  // Set default values when data is loaded
  useEffect(() => {
    if (modeles.length > 0 && !formData.id_modele) {
      // Get latest modele (sorted by date_creation desc)
      const sortedModeles = [...modeles].sort((a, b) =>
        new Date(b.date_creation).getTime() - new Date(a.date_creation).getTime()
      );
      setFormData((prev) => ({ ...prev, id_modele: sortedModeles[0].id_modele }));
    }
  }, [modeles, formData.id_modele]);

  useEffect(() => {
    if (cibles.length > 0 && !formData.id_cible) {
      // Get latest cible (sorted by created_at desc)
      const sortedCibles = [...cibles].sort((a, b) => {
        const dateStrA = a.date_creation || a.created_at;
        const dateStrB = b.date_creation || b.created_at;
        const dateA = dateStrA ? new Date(dateStrA).getTime() : 0;
        const dateB = dateStrB ? new Date(dateStrB).getTime() : 0;
        return dateB - dateA;
      });
      setFormData((prev) => ({ ...prev, id_cible: sortedCibles[0].id_cible || sortedCibles[0].id }));
    }
  }, [cibles, formData.id_cible]);

  // Pre-fill form when duplicating
  useEffect(() => {
    if (duplicateData && isOpen) {
      setFormData({
        nom_campagne: `${duplicateData.nom_campagne} (copie)`,
        description: duplicateData.description || '',
        date_debut: '',
        date_fin: '',
        id_modele: duplicateData.id_modele,
        id_cible: duplicateData.id_cible,
      });
    }
  }, [duplicateData, isOpen]);

  // Create campaign mutation
  const createMutation = useMutation({
    mutationFn: (data: typeof formData) => apiClient.request(campaignsApi.create(data)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
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
    });
    setErrors({});
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

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    createMutation.mutate(formData);
  };

  const handleEscape = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && isOpen) {
      handleClose();
    }
  };

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen]);

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
                    <option key={cible.id_cible || cible.id} value={cible.id_cible || cible.id}>
                      {cible.nom_cible} ({cible.source})
                    </option>
                  ))}
                </select>
              )}
              {errors.id_cible && (
                <p className="mt-1 text-xs text-red-500">{errors.id_cible}</p>
              )}
            </div>
          </div>

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
              disabled={createMutation.isPending}
              className="px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {createMutation.isPending && <LoadingSpinner size="sm" />}
              {createMutation.isPending ? 'Création...' : (duplicateData ? 'Dupliquer' : 'Créer la campagne')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
