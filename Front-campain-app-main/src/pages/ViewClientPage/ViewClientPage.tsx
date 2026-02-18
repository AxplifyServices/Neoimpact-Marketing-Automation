import { ArrowLeft, Edit } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { clientsApi } from '@/lib/api/definitions/clients.api';
import { getApiClient } from '@/lib/api/api-client';
import { Button } from '@/components/ui/button';
import Toast from '@/components/Toast';
import type { ClientAPIResponse } from '@/types/client.types';

export default function ViewClientPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const apiClient = getApiClient();

  const [toast, setToast] = useState<{
    isOpen: boolean;
    title: string;
    message?: string;
    type?: 'success' | 'error' | 'warning';
  }>({
    isOpen: false,
    title: '',
  });

  // Fetch client data
  const { data: clientData, isLoading } = useQuery<{ rows: ClientAPIResponse[] }>({
    queryKey: ['client', id],
    queryFn: () => apiClient.request(clientsApi.findById(id!)),
    enabled: !!id,
  });

  const client = clientData?.rows?.[0];

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
        <div className="max-w-7xl mx-auto">
          <p className="text-gray-500">Chargement...</p>
        </div>
      </div>
    );
  }

  if (!client) {
    return (
      <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
        <div className="max-w-7xl mx-auto">
          <p className="text-gray-500">Client non trouvé</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />

      <div className="max-w-7xl mx-auto">
        {/* Back button */}
        <button
          onClick={() => navigate('/clients')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="text-sm font-medium">Retour à la liste</span>
        </button>

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">
              {client.Nom} {client.Prenom}
            </h1>
            <p className="text-gray-600 text-xs sm:text-sm">{client.ID_Client}</p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={() => navigate(`/clients/${id}/edit`)}
            >
              <Edit className="w-4 h-4 mr-2" />
              Modifier
            </Button>
          </div>
        </div>

        {/* Client details */}
        <div className="space-y-6">
          {/* Required Information */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Informations obligatoires</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <p className="text-xs text-gray-500 mb-1">ID Client</p>
                <p className="text-sm font-medium text-gray-900">{client.ID_Client}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1">Téléphone</p>
                <p className="text-sm font-medium text-gray-900">{client.Numero_Tel}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1">Email</p>
                <p className="text-sm font-medium text-gray-900">{client.Mail}</p>
              </div>
            </div>
          </div>

          {/* Personal Information */}
          {(client.Nom || client.Prenom || client.Qualite || client.Age) && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Informations personnelles</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {client.Nom && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Nom</p>
                    <p className="text-sm font-medium text-gray-900">{client.Nom}</p>
                  </div>
                )}
                {client.Prenom && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Prénom</p>
                    <p className="text-sm font-medium text-gray-900">{client.Prenom}</p>
                  </div>
                )}
                {client.Qualite && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Qualité</p>
                    <p className="text-sm font-medium text-gray-900">{client.Qualite}</p>
                  </div>
                )}
                {client.Age && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Âge</p>
                    <p className="text-sm font-medium text-gray-900">{client.Age}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Banking Information */}
          {(client.Region || client.Agence || client.Gestionnaire || client.STATUT_CLIENT) && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Informations bancaires</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {client.Region && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Région</p>
                    <p className="text-sm font-medium text-gray-900">{client.Region}</p>
                  </div>
                )}
                {client.Agence && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Agence</p>
                    <p className="text-sm font-medium text-gray-900">{client.Agence}</p>
                  </div>
                )}
                {client.Gestionnaire && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Gestionnaire</p>
                    <p className="text-sm font-medium text-gray-900">{client.Gestionnaire}</p>
                  </div>
                )}
                {client.STATUT_CLIENT && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Statut</p>
                    <p className="text-sm font-medium text-gray-900">{client.STATUT_CLIENT}</p>
                  </div>
                )}
                {client.Segment_actuel && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Segment</p>
                    <p className="text-sm font-medium text-gray-900">{client.Segment_actuel}</p>
                  </div>
                )}
                {client.Canal_acquisition && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Canal d'acquisition</p>
                    <p className="text-sm font-medium text-gray-900">{client.Canal_acquisition}</p>
                  </div>
                )}
                {client.Anciennete !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Ancienneté</p>
                    <p className="text-sm font-medium text-gray-900">{client.Anciennete} ans</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Account Status */}
          {(client.Dossier_Complet || client.Validation_KYC || client.Activation_du_compte || client.Activation_carte) && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Statuts compte</h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {client.Dossier_Complet && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Dossier complet</p>
                    <p className="text-sm font-medium text-gray-900">{client.Dossier_Complet}</p>
                  </div>
                )}
                {client.Validation_KYC && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Validation KYC</p>
                    <p className="text-sm font-medium text-gray-900">{client.Validation_KYC}</p>
                  </div>
                )}
                {client.Activation_du_compte && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Activation compte</p>
                    <p className="text-sm font-medium text-gray-900">{client.Activation_du_compte}</p>
                  </div>
                )}
                {client.Activation_carte && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Activation carte</p>
                    <p className="text-sm font-medium text-gray-900">{client.Activation_carte}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Products */}
          {(client.Carte_Actuelle || client.Assurance_Actuelle || client.Epargne || client.revenu_domicilie) && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Produits et services</h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {client.Carte_Actuelle && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Carte</p>
                    <p className="text-sm font-medium text-gray-900">{client.Carte_Actuelle}</p>
                  </div>
                )}
                {client.Assurance_Actuelle && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Assurance</p>
                    <p className="text-sm font-medium text-gray-900">{client.Assurance_Actuelle}</p>
                  </div>
                )}
                {client.Epargne && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Épargne</p>
                    <p className="text-sm font-medium text-gray-900">{client.Epargne}</p>
                  </div>
                )}
                {client.revenu_domicilie && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Revenu domicilié</p>
                    <p className="text-sm font-medium text-gray-900">{client.revenu_domicilie}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Transaction Metrics */}
          {(client.nb_transaction !== undefined || client.vol_transaction !== undefined) && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Métriques de transaction</h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {client.nb_transaction !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Nb transactions</p>
                    <p className="text-sm font-medium text-gray-900">{client.nb_transaction}</p>
                  </div>
                )}
                {client.vol_transaction !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Vol transactions</p>
                    <p className="text-sm font-medium text-gray-900">{client.vol_transaction.toLocaleString('fr-FR')} DH</p>
                  </div>
                )}
                {client.nb_retrait_gab !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Nb retrait GAB</p>
                    <p className="text-sm font-medium text-gray-900">{client.nb_retrait_gab}</p>
                  </div>
                )}
                {client.vol_retrait_gab !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Vol retrait GAB</p>
                    <p className="text-sm font-medium text-gray-900">{client.vol_retrait_gab.toLocaleString('fr-FR')} DH</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Financial Information */}
          {(client.encours_moyen !== undefined || client.encours_global !== undefined) && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Informations financières</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {client.solde_moyen_depots !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Solde moyen dépôts</p>
                    <p className="text-sm font-medium text-gray-900">{client.solde_moyen_depots.toLocaleString('fr-FR')} DH</p>
                  </div>
                )}
                {client.encours_moyen !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Encours moyen</p>
                    <p className="text-sm font-medium text-gray-900">{client.encours_moyen.toLocaleString('fr-FR')} DH</p>
                  </div>
                )}
                {client.encours_global !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Encours global</p>
                    <p className="text-sm font-medium text-gray-900">{client.encours_global.toLocaleString('fr-FR')} DH</p>
                  </div>
                )}
                {client.montant_revenu !== undefined && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Montant revenu</p>
                    <p className="text-sm font-medium text-gray-900">{client.montant_revenu.toLocaleString('fr-FR')} DH</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
