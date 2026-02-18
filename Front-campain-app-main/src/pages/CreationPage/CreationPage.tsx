import { Target, ChartColumn, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCreationData } from './useCreationData';
import { ciblesApi } from '@/lib/api/definitions/cibles.api';
import { getApiClient } from '@/lib/api/api-client';
import ConfirmDialog from '../../components/ConfirmDialog';
import Toast from '../../components/Toast';
import CibleForm from './CibleForm';
import ModeleForm from './ModeleForm';

type Tab = 'cibles' | 'modeles';

export default function CreationPage() {
  const [activeTab, setActiveTab] = useState<Tab>('cibles');
  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; cibleId?: string; cibleName?: string }>({
    isOpen: false,
  });
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' | 'warning' }>({
    isOpen: false,
    title: '',
  });

  const { cibles } = useCreationData();
  const queryClient = useQueryClient();
  const apiClient = getApiClient();

  // Mutation for creating a cible
  const createCibleMutation = useMutation({
    mutationFn: (data: { name: string; type: string }) => {
      // Build filter object from form data (can be extended later)
      const filtre: Record<string, any> = {};

      return apiClient.request(
        ciblesApi.createFromDB({
          nom_cible: data.name,
          filtre,
        })
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cibles'] });
      setToast({
        isOpen: true,
        title: 'Cible créée',
        message: 'La cible a été créée avec succès',
        type: 'success',
      });
    },
    onError: () => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Une erreur est survenue lors de la création de la cible',
        type: 'error',
      });
    },
  });

  // Mutation for deleting a cible
  const deleteCibleMutation = useMutation({
    mutationFn: (id: string) => apiClient.request(ciblesApi.delete(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cibles'] });
      setToast({
        isOpen: true,
        title: 'Cible supprimée',
        message: `La cible "${deleteDialog.cibleName}" a été supprimée`,
        type: 'success',
      });
      setDeleteDialog({ isOpen: false });
    },
    onError: () => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Une erreur est survenue lors de la suppression de la cible',
        type: 'error',
      });
    },
  });

  const handleCreateCible = (data: any) => {
    createCibleMutation.mutate(data);
  };

  const handleCreateModel = () => {
    // For now, just show toast (Modèle API not implemented yet)
    setToast({
      isOpen: true,
      title: 'Modèle créé',
      message: 'Le modèle a été créé avec succès',
      type: 'success',
    });
  };

  const handleShowDetails = (cibleName: string) => {
    setToast({
      isOpen: true,
      title: 'Détails de la cible',
      message: `Affichage des détails pour "${cibleName}"`,
    });
  };

  const handleDeleteCible = (cibleId: string, cibleName: string) => {
    setDeleteDialog({ isOpen: true, cibleId, cibleName });
  };

  const confirmDelete = () => {
    if (deleteDialog.cibleId) {
      deleteCibleMutation.mutate(deleteDialog.cibleId);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />

      <ConfirmDialog
        isOpen={deleteDialog.isOpen}
        onClose={() => setDeleteDialog({ isOpen: false })}
        onConfirm={confirmDelete}
        title="Supprimer la cible"
        message={`Êtes-vous sûr de vouloir supprimer la cible "${deleteDialog.cibleName}" ? Cette action est irréversible.`}
        confirmText="Supprimer"
        cancelText="Annuler"
        type="danger"
      />

      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2 sm:p-3 bg-pink-100 rounded-xl">
            <Target className="w-5 h-5 sm:w-6 sm:h-6 text-pink-600" />
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">Création</h1>
        </div>
        <p className="text-gray-600 text-sm sm:text-base">Gérer les Cibles et les modèles d'actions qui sont vos briques.</p>
      </div>

      {/* Tabs */}
      <div className="flex bg-gray-100 rounded-full p-1.5 mb-6 sm:mb-8 w-full sm:w-auto sm:inline-flex">
        <button
          type="button"
          onClick={() => setActiveTab('cibles')}
          className={`flex-1 sm:flex-none px-4 sm:px-5 py-2 rounded-full font-semibold transition-all flex items-center justify-center gap-2 ${
            activeTab === 'cibles'
              ? 'bg-gradient-to-r from-pink-100 to-purple-100 text-purple-700 shadow-sm'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          <span className="text-xl">🎯</span>
          <span className="text-sm sm:text-base">Cibles</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('modeles')}
          className={`flex-1 sm:flex-none px-4 sm:px-5 py-2 rounded-full font-semibold transition-all flex items-center justify-center gap-2 ${
            activeTab === 'modeles'
              ? 'bg-gradient-to-r from-pink-100 to-purple-100 text-purple-700 shadow-sm'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          <span className="text-xl">📊</span>
          <span className="text-sm sm:text-base">Modèles</span>
        </button>
      </div>

      {/* Cibles Tab Content */}
      {activeTab === 'cibles' && (
        <div>
          {/* Cibles Header */}
          <div className="flex items-center gap-3 mb-4 sm:mb-6">
            <Target className="w-5 h-5 sm:w-6 sm:h-6 text-pink-600" />
            <h2 className="text-xl sm:text-2xl font-bold text-gray-900">Cibles</h2>
          </div>

          {/* Create Cible Form */}
          <CibleForm onSubmit={handleCreateCible} />

          {/* Cibles List */}
          <div className="bg-white rounded-2xl p-4 sm:p-6 lg:p-8 shadow-sm border border-gray-100">
            <h3 className="text-lg sm:text-xl font-bold text-gray-900 mb-4 sm:mb-6">Liste des cibles (1)</h3>

            <div className="space-y-4">
              {cibles.map((cible) => (
                <div
                  key={cible.id}
                  className="bg-gray-50 rounded-xl p-4 sm:p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 hover:bg-gray-100 transition-colors"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-8 w-full sm:w-auto">
                    <span className="font-semibold text-gray-900 text-sm sm:text-base">{cible.code}</span>
                    <span className="text-gray-700 text-sm sm:text-base">{cible.name}</span>
                    <span className="text-gray-700 text-sm sm:text-base">{cible.type}</span>
                  </div>
                  <div className="flex items-center gap-3 sm:gap-4 w-full sm:w-auto justify-between sm:justify-end">
                    <span className="text-gray-500 text-xs sm:text-sm">{cible.timestamp}</span>
                    <button
                      type="button"
                      onClick={() => handleShowDetails(cible.name)}
                      className="text-gray-700 hover:text-gray-900 font-medium cursor-pointer text-sm sm:text-base"
                    >
                      Détails
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteCible(cible.id, cible.name)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors cursor-pointer"
                    >
                      <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Modèles Tab Content */}
      {activeTab === 'modeles' && (
        <div>
          <div className="flex items-center gap-3 mb-4 sm:mb-6">
            <ChartColumn className="w-5 h-5 sm:w-6 sm:h-6 text-pink-600" />
            <h2 className="text-xl sm:text-2xl font-bold text-gray-900">Modèles</h2>
          </div>

          {/* Create Modèle Form */}
          <ModeleForm onSubmit={handleCreateModel} />
        </div>
      )}
    </div>
  );
}
