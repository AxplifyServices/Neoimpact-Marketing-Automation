import { ArrowLeft } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { clientsApi } from '@/lib/api/definitions/clients.api';
import { metaApi } from '@/lib/api/definitions/meta.api';
import { getApiClient } from '@/lib/api/api-client';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import Toast from '@/components/Toast';
import type { ClientFormData, ClientAPIResponse } from '@/types/client.types';
import type { ClientFormMetadata, FieldType } from '@/types/form-metadata.types';

export default function CreateClientPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const apiClient = getApiClient();

  const isEditing = !!id;

  // Form state
  const [formData, setFormData] = useState<ClientFormData>({
    ID_Client: '',
    Numero_Tel: '',
    Mail: '',
    Nom: '',
    Prenom: '',
    Qualite: '',
    Age: '',
    Region: '',
    Agence: '',
    Gestionnaire: '',
    STATUT_CLIENT: '',
    Segment_actuel: '',
    Canal_acquisition: '',
    Anciennete: '',
    Dossier_Complet: '',
    Validation_KYC: '',
    Activation_du_compte: '',
    Activation_carte: '',
    Carte_Actuelle: '',
    Assurance_Actuelle: '',
    Epargne: '',
    revenu_domicilie: '',
    nb_transaction: '',
    vol_transaction: '',
    nb_retrait_gab: '',
    vol_retrait_gab: '',
    nb_transaction_ecom: '',
    vol_transaction_ecom: '',
    nb_virement: '',
    vol_virement: '',
    solde_moyen_depots: '',
    encours_moyen: '',
    encours_global: '',
    encours_conso: '',
    encours_immo: '',
    montant_revenu: '',
  });

  // Toast notification state
  const [toast, setToast] = useState<{
    isOpen: boolean;
    title: string;
    message?: string;
    type?: 'success' | 'error' | 'warning';
  }>({
    isOpen: false,
    title: '',
  });

  // Fetch existing client data if editing
  const { data: clientResponse } = useQuery<{ rows: ClientAPIResponse[] }>({
    queryKey: ['client', id],
    queryFn: () => apiClient.request(clientsApi.findById(id!)),
    enabled: isEditing,
  });

  const clientData = clientResponse?.rows?.[0];

  // Fetch form metadata
  const { data: fieldMetadata, isLoading: metadataLoading } = useQuery<ClientFormMetadata>({
    queryKey: ['client-form-metadata'],
    queryFn: () => apiClient.request(metaApi.getClientFormMetadata()),
  });

  // Populate form when editing
  useEffect(() => {
    if (isEditing && clientData) {
      setFormData({
        ID_Client: clientData.ID_Client || '',
        Numero_Tel: clientData.Numero_Tel || '',
        Mail: clientData.Mail || '',
        Nom: clientData.Nom || '',
        Prenom: clientData.Prenom || '',
        Qualite: clientData.Qualite || '',
        Age: clientData.Age?.toString() || '',
        Region: clientData.Region || '',
        Agence: clientData.Agence || '',
        Gestionnaire: clientData.Gestionnaire || '',
        STATUT_CLIENT: clientData.STATUT_CLIENT || '',
        Segment_actuel: clientData.Segment_actuel || '',
        Canal_acquisition: clientData.Canal_acquisition || '',
        Anciennete: clientData.Anciennete?.toString() || '',
        Dossier_Complet: clientData.Dossier_Complet || '',
        Validation_KYC: clientData.Validation_KYC || '',
        Activation_du_compte: clientData.Activation_du_compte || '',
        Activation_carte: clientData.Activation_carte || '',
        Carte_Actuelle: clientData.Carte_Actuelle || '',
        Assurance_Actuelle: clientData.Assurance_Actuelle || '',
        Epargne: clientData.Epargne || '',
        revenu_domicilie: clientData.revenu_domicilie || '',
        nb_transaction: clientData.nb_transaction?.toString() || '',
        vol_transaction: clientData.vol_transaction?.toString() || '',
        nb_retrait_gab: clientData.nb_retrait_gab?.toString() || '',
        vol_retrait_gab: clientData.vol_retrait_gab?.toString() || '',
        nb_transaction_ecom: clientData.nb_transaction_ecom?.toString() || '',
        vol_transaction_ecom: clientData.vol_transaction_ecom?.toString() || '',
        nb_virement: clientData.nb_virement?.toString() || '',
        vol_virement: clientData.vol_virement?.toString() || '',
        solde_moyen_depots: clientData.solde_moyen_depots?.toString() || '',
        encours_moyen: clientData.encours_moyen?.toString() || '',
        encours_global: clientData.encours_global?.toString() || '',
        encours_conso: clientData.encours_conso?.toString() || '',
        encours_immo: clientData.encours_immo?.toString() || '',
        montant_revenu: clientData.montant_revenu?.toString() || '',
      });
    }
  }, [isEditing, clientData]);

  // Field update handler
  const updateField = (field: keyof ClientFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Render field based on metadata type
  const renderField = (fieldName: string, metadata: FieldType) => {
    const value = formData[fieldName as keyof ClientFormData] || '';
    const isRequired = ['ID_Client', 'Numero_Tel', 'Mail'].includes(fieldName);
    const fieldLabel = fieldName.replace(/_/g, ' ');

    // Categorical field - render dropdown
    if (Array.isArray(metadata)) {
      return (
        <div key={fieldName} className="space-y-2">
          <Label htmlFor={fieldName}>
            {fieldLabel}
            {isRequired && <span className="text-red-500 ml-1">*</span>}
          </Label>
          <select
            id={fieldName}
            value={value}
            onChange={(e) => updateField(fieldName as keyof ClientFormData, e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
          >
            <option value="">Sélectionner...</option>
            {metadata.map(option => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </div>
      );
    }

    // Numeric field - render number input
    if (metadata === "Numérique") {
      return (
        <div key={fieldName} className="space-y-2">
          <Label htmlFor={fieldName}>
            {fieldLabel}
            {isRequired && <span className="text-red-500 ml-1">*</span>}
          </Label>
          <Input
            id={fieldName}
            type="number"
            value={value}
            onChange={(e) => updateField(fieldName as keyof ClientFormData, e.target.value)}
            placeholder={`Entrer ${fieldLabel.toLowerCase()}`}
          />
        </div>
      );
    }

    // Text field - render text/email/tel input
    const inputType = fieldName === 'Mail' ? 'email' : fieldName === 'Numero_Tel' ? 'tel' : 'text';
    return (
      <div key={fieldName} className="space-y-2">
        <Label htmlFor={fieldName}>
          {fieldLabel}
          {isRequired && <span className="text-red-500 ml-1">*</span>}
        </Label>
        <Input
          id={fieldName}
          type={inputType}
          value={value}
          onChange={(e) => updateField(fieldName as keyof ClientFormData, e.target.value)}
          placeholder={`Entrer ${fieldLabel.toLowerCase()}`}
        />
      </div>
    );
  };

  // Create/Update mutation
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      if (isEditing && id) {
        const rowId = (clientData as any)?.__rowid__ ?? (clientData as any)?.rowid;
        if (rowId === undefined || rowId === null) {
          throw new Error('Rowid introuvable pour la mise Ã  jour');
        }

        const entries = Object.entries(data) as Array<[string, any]>;
        if (entries.length === 0) {
          return { ok: true };
        }

        await Promise.all(
          entries.map(([col, value]) => {
            const sanitizedValue =
              typeof value === 'number' || typeof value === 'string' ? value : String(value);
            return apiClient.request(
              clientsApi.updateCell({
                rowid: rowId,
                col,
                value: sanitizedValue,
              })
            );
          })
        );

        return { ok: true };
      }

      return apiClient.request(clientsApi.create(data));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      if (isEditing && id) {
        queryClient.invalidateQueries({ queryKey: ['client', id] });
      }
      setToast({
        isOpen: true,
        title: 'Succès',
        message: isEditing ? 'Client mis à jour avec succès' : 'Client créé avec succès',
        type: 'success',
      });
      setTimeout(() => navigate('/clients'), 1500);
    },
    onError: (error: any) => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: error.message || `Impossible de ${isEditing ? 'mettre à jour' : 'créer'} le client`,
        type: 'error',
      });
    },
  });

  // Submit handler
  const handleSubmit = () => {
    // Validate mandatory fields
    if (!formData.ID_Client?.trim()) {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'L\'ID Client est obligatoire',
        type: 'error',
      });
      return;
    }

    if (!formData.Numero_Tel?.trim()) {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Le numéro de téléphone est obligatoire',
        type: 'error',
      });
      return;
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!formData.Mail?.trim() || !emailRegex.test(formData.Mail)) {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'L\'adresse email est obligatoire et doit être valide',
        type: 'error',
      });
      return;
    }

    // Check metadata is loaded
    if (!fieldMetadata) {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Métadonnées non chargées',
        type: 'error',
      });
      return;
    }

    // Build payload using metadata for type conversion
    const payload: any = {};

    Object.keys(fieldMetadata).forEach(fieldName => {
      const value = formData[fieldName as keyof ClientFormData];
      const metadata = fieldMetadata[fieldName];

      // Skip empty values
      if (!value || (typeof value === 'string' && value.trim() === '')) {
        return;
      }

      // Convert based on metadata type
      if (metadata === "Numérique") {
        const numValue = parseFloat(value);
        if (!isNaN(numValue)) {
          payload[fieldName] = numValue;
        }
      } else {
        // Text or categorical - just trim and add
        payload[fieldName] = typeof value === 'string' ? value.trim() : value;
      }
    });

    createMutation.mutate(payload);
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

      <div className="max-w-7xl mx-auto">
        {/* Back button */}
        <button
          onClick={() => navigate('/clients')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="text-sm font-medium">Retour à la liste</span>
        </button>

        {/* Page title */}
        <div className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">
            {isEditing ? 'Modifier le client' : 'Nouveau client'}
          </h1>
          <p className="text-gray-600 text-xs sm:text-sm">
            {isEditing ? 'Modifiez les informations du client' : 'Créez un nouveau client en remplissant les champs obligatoires'}
          </p>
        </div>

        {/* Form */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-6">
          {/* Loading state */}
          {metadataLoading ? (
            <div className="text-center py-12">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900"></div>
              <p className="mt-4 text-sm text-gray-600">Chargement du formulaire...</p>
            </div>
          ) : !fieldMetadata ? (
            <div className="text-center py-8 text-red-600">
              <p>Erreur: Impossible de charger les métadonnées du formulaire</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.keys(fieldMetadata).map((fieldName) => {
                const metadata = fieldMetadata[fieldName];
                return renderField(fieldName, metadata);
              })}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-4 pt-6 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/clients')}
              disabled={createMutation.isPending}
            >
              Annuler
            </Button>
            <Button
              type="button"
              onClick={handleSubmit}
              disabled={createMutation.isPending || metadataLoading}
              className="bg-slate-900 text-white hover:bg-slate-800"
            >
              {createMutation.isPending
                ? 'En cours...'
                : isEditing
                ? 'Mettre à jour'
                : 'Créer le client'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
