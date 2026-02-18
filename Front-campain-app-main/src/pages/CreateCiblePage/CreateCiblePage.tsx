import { ArrowLeft, Plus, Trash2, Database, FileText } from 'lucide-react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useState, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ciblesApi } from '@/lib/api/definitions/cibles.api';
import { metaApi } from '@/lib/api/definitions/meta.api';
import { getApiClient } from '@/lib/api/api-client';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { MultiSelect } from '@/components/ui/multi-select';
import Toast from '@/components/Toast';
import { FileUpload } from '@/components/custom/FileUpload';

type CibleMetaResponse = Record<string, string[] | 'Numérique'>;

type FilterKind = 'numeric' | 'categorical';

interface CibleFilter {
  id: string;
  column: string;
  min?: string;
  max?: string;
  values?: string[];
}

interface CibleDetail {
  id_cible: string;
  nom_cible: string;
  source: string;
  date_creation: string;
  filtre?: Record<string, any> | string;
  chemin?: string;
}

interface DuplicateState {
  duplicateId?: string;
}

const formatFieldLabel = (field: string) => {
  // Convert snake_case or camelCase to readable format
  return field
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

export default function CreateCiblePage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const isEditing = Boolean(id);
  const duplicateId = (location.state as DuplicateState | null)?.duplicateId;
  const isDuplicating = Boolean(duplicateId);
  const sourceId = isEditing ? id : duplicateId;
  const apiClient = getApiClient();
  const queryClient = useQueryClient();

  const [creationMode, setCreationMode] = useState<'DB' | 'FILE'>('DB');
  const [nomCible, setNomCible] = useState('');
  const [filters, setFilters] = useState<CibleFilter[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string>('');
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' }>({
    isOpen: false,
    title: '',
  });
  const isFileModeDisabled = false;

  // Fetch cible metadata (fields and their possible values)
  const { data: cibleMeta, isLoading: metaLoading } = useQuery<CibleMetaResponse>({
    queryKey: ['cible-meta'],
    queryFn: () => apiClient.request<CibleMetaResponse>(metaApi.getCibleMeta()),
  });

  // Derive field lists from meta data
  const { numFields, catFields, allFields, valuesByField } = useMemo(() => {
    if (!cibleMeta) {
      return { numFields: [] as string[], catFields: [] as string[], allFields: [] as string[], valuesByField: {} as Record<string, string[]> };
    }

    const numFields: string[] = [];
    const catFields: string[] = [];
    const valuesByField: Record<string, string[]> = {};

    Object.entries(cibleMeta).forEach(([field, value]) => {
      if (value === 'Numérique') {
        numFields.push(field);
      } else if (Array.isArray(value)) {
        catFields.push(field);
        valuesByField[field] = value;
      }
    });

    return {
      numFields,
      catFields,
      allFields: [...catFields, ...numFields],
      valuesByField,
    };
  }, [cibleMeta]);

  const getFieldKind = (field: string): FilterKind => numFields.includes(field) ? 'numeric' : 'categorical';

  // Fetch existing cible data if editing or duplicating
  const { data: cibleData, isLoading: cibleLoading } = useQuery<CibleDetail>({
    queryKey: ['cible', sourceId],
    queryFn: () => apiClient.request<CibleDetail>(ciblesApi.findById(sourceId!)),
    enabled: !!sourceId,
  });

  // Fetch existing filter data if editing or duplicating
  const { data: filterData } = useQuery({
    queryKey: ['cible-filter', sourceId],
    queryFn: () => apiClient.request(ciblesApi.getFiltre(sourceId!)),
    enabled: !!sourceId,
  });

  // Create/Update cible mutation (DB mode)
  const createMutation = useMutation({
    mutationFn: async (data: { nom_cible: string; filtre: Record<string, any> }) => {
      if (isEditing && id) {
        const basePayload: CibleDetail = cibleData || {
          id_cible: id,
          nom_cible: '',
          source: 'DB',
          date_creation: '',
        };
        return apiClient.request(ciblesApi.update(id, {
          ...basePayload,
          nom_cible: data.nom_cible,
          filtre: data.filtre,
        }));
      }
      return apiClient.request(ciblesApi.createFromDB(data));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cibles'] });
      queryClient.invalidateQueries({ queryKey: ['cible', id] });
      setToast({
        isOpen: true,
        title: 'Succes',
        message: isEditing ? 'Cible mise a jour avec succes' : 'Cible creee avec succes',
        type: 'success',
      });
      setTimeout(() => navigate('/cibles'), 1500);
    },
    onError: () => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: isEditing ? 'Impossible de mettre a jour la cible' : 'Impossible de creer la cible',
        type: 'error',
      });
    },
  });

  // Create cible from file mutation (FILE mode)
  const createFileMutation = useMutation({
    mutationFn: async (data: { nom_cible: string; file: File }) => {
      return apiClient.request(ciblesApi.createFromFile(data.nom_cible, data.file));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cibles'] });
      setToast({
        isOpen: true,
        title: 'Succes',
        message: 'Cible creee avec succes a partir du fichier',
        type: 'success',
      });
      setTimeout(() => navigate('/cibles'), 1500);
    },
    onError: (error: any) => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: error.message || 'Impossible de creer la cible a partir du fichier',
        type: 'error',
      });
    },
  });

  // Populate form when editing
  useEffect(() => {
    if ((isEditing || isDuplicating) && cibleData) {
      setNomCible(cibleData.nom_cible || '');
    }
  }, [isEditing, isDuplicating, cibleData]);

  // Populate filters when editing or duplicating
  useEffect(() => {
    if (isEditing || isDuplicating) {
      const nextFilters: CibleFilter[] = [];

      try {
        const sourceFiltre = cibleData?.filtre ?? filterData;

        if (!sourceFiltre) {
          return;
        }

        const parsedFiltre = typeof sourceFiltre === 'string'
          ? JSON.parse(sourceFiltre)
          : sourceFiltre;

        Object.entries(parsedFiltre).forEach(([column, value]: [string, any]) => {
          if (Array.isArray(value)) {
            nextFilters.push({
              id: Date.now().toString() + Math.random(),
              column,
              values: value.map((item) => String(item)),
            });
            return;
          }

          if (value && typeof value === 'object') {
            if ('values' in value && Array.isArray(value.values)) {
              nextFilters.push({
                id: Date.now().toString() + Math.random(),
                column,
                values: value.values.map((item: unknown) => String(item)),
              });
              return;
            }

            if ('min' in value || 'max' in value) {
              nextFilters.push({
                id: Date.now().toString() + Math.random(),
                column,
                min: value.min !== undefined ? String(value.min) : '',
                max: value.max !== undefined ? String(value.max) : '',
              });
            }
          }
        });

        setFilters(nextFilters);
      } catch (error) {
        console.error('Error parsing filters:', error);
      }
    }
  }, [isEditing, isDuplicating, cibleData, filterData]);

  const addFilter = () => {
    const defaultColumn = allFields[0] || '';
    setFilters([
      ...filters,
      {
        id: Date.now().toString(),
        column: defaultColumn,
        min: '',
        max: '',
        values: [],
      },
    ]);
  };

  const removeFilter = (filterId: string) => {
    setFilters(filters.filter((filter) => filter.id !== filterId));
  };

  const updateFilterColumn = (filterId: string, column: string) => {
    const kind = getFieldKind(column);
    setFilters(filters.map((filter) =>
      filter.id === filterId
        ? {
          ...filter,
          column,
          min: kind === 'numeric' ? filter.min ?? '' : '',
          max: kind === 'numeric' ? filter.max ?? '' : '',
          values: kind === 'categorical' ? [] : [],
        }
        : filter
    ));
  };

  const updateNumericFilter = (filterId: string, field: 'min' | 'max', value: string) => {
    setFilters(filters.map((filter) =>
      filter.id === filterId ? { ...filter, [field]: value } : filter
    ));
  };

  const updateCategoricalValues = (filterId: string, values: string[]) => {
    setFilters(filters.map((filter) => (
      filter.id === filterId ? { ...filter, values } : filter
    )));
  };

  const handleFileSelect = (file: File | null) => {
    setSelectedFile(file);
    setFileError('');

    if (file) {
      // Client-side validation
      const validExtensions = ['.csv', '.xlsx'];
      const extension = '.' + file.name.split('.').pop()?.toLowerCase();

      if (!validExtensions.includes(extension)) {
        setFileError('Format de fichier non supporte. Utilisez CSV ou XLSX.');
        setSelectedFile(null);
        return;
      }

      if (file.size > 10 * 1024 * 1024) {
        const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
        setFileError(`Le fichier est trop volumineux (${sizeMB} MB). Maximum 10 MB.`);
        setSelectedFile(null);
        return;
      }
    }
  };

  const handleSubmit = () => {
    if (!nomCible.trim()) {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Veuillez saisir un nom pour la cible',
        type: 'error',
      });
      return;
    }

    // File mode validation and submission
    if (creationMode === 'FILE') {
      if (isFileModeDisabled) {
        setToast({
          isOpen: true,
          title: 'Information',
          message: 'La creation de cible par fichier est temporairement desactivee.',
          type: 'error',
        });
        return;
      }
      if (!selectedFile) {
        setToast({
          isOpen: true,
          title: 'Erreur',
          message: 'Veuillez selectionner un fichier',
          type: 'error',
        });
        return;
      }

      createFileMutation.mutate({
        nom_cible: nomCible,
        file: selectedFile,
      });
      return;
    }

    // DB mode validation and submission
    const filtre: Record<string, any> = {};

    filters.forEach((filter) => {
      const column = filter.column.trim();
      if (!column) {
        return;
      }

      if (getFieldKind(column) === 'numeric') {
        if (!filter.min && !filter.max) {
          return;
        }

        filtre[column] = {
          ...(filter.min && { min: parseFloat(filter.min) }),
          ...(filter.max && { max: parseFloat(filter.max) }),
        };
        return;
      }

      if (filter.values && filter.values.length > 0) {
        filtre[column] = { values: filter.values };
      }
    });

    createMutation.mutate({
      nom_cible: nomCible,
      filtre,
    });
  };

  if (metaLoading || ((isEditing || isDuplicating) && cibleLoading)) {
    return (
      <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
        <div className="max-w-7xl mx-auto">
          <p>Chargement...</p>
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
        <button
          onClick={() => navigate('/cibles')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>Retour aux cibles</span>
        </button>

        <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-8">
          {isEditing ? 'Modifier la cible' : 'Creer une nouvelle cible'}
        </h1>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-6">
          {/* Mode Selection Tabs (only show when creating, not editing) */}
          {!isEditing && (
            <div className="flex gap-2 p-1 bg-gray-100 rounded-lg">
              <button
                onClick={() => setCreationMode('DB')}
                className={`flex-1 px-4 py-2 rounded-md transition-colors flex items-center justify-center gap-2 ${
                  creationMode === 'DB'
                    ? 'bg-white shadow-sm font-semibold text-gray-900'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                <Database className="w-4 h-4" />
                Base de donnees
              </button>
              <button
                onClick={() => setCreationMode('FILE')}
                disabled={isFileModeDisabled}
                className={`flex-1 px-4 py-2 rounded-md transition-colors flex items-center justify-center gap-2 ${
                  creationMode === 'FILE'
                    ? 'bg-white shadow-sm font-semibold text-gray-900'
                    : 'text-gray-600 hover:text-gray-900'
                } ${isFileModeDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <FileText className="w-4 h-4" />
                Fichier
              </button>
            </div>
          )}

          <div>
            <Label htmlFor="nom_cible">Nom de la cible</Label>
            <Input
              id="nom_cible"
              value={nomCible}
              onChange={(e) => setNomCible(e.target.value)}
              placeholder="Ex: Clients actifs 2024"
              className="mt-2"
            />
          </div>

          {creationMode === 'DB' ? (
            <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Filtres</h3>
              <Button onClick={addFilter} variant="outline" size="sm">
                <Plus className="w-4 h-4 mr-2" />
                Ajouter un filtre
              </Button>
            </div>

            <div className="space-y-4">
              {filters.map((filter) => {
                const kind = getFieldKind(filter.column);
                const availableModalities = filter.column ? (valuesByField[filter.column] || []) : [];

                return (
                  <div key={filter.id} className="p-4 border rounded-lg space-y-4">
                    <div className="flex items-start gap-4">
                      <div className="flex-1">
                        <Label>Colonne</Label>
                        <select
                          value={filter.column}
                          onChange={(e) => updateFilterColumn(filter.id, e.target.value)}
                          className="mt-2 w-full px-3 py-2 border rounded-md"
                        >
                          <option value="">Sélectionner...</option>
                          {!allFields.includes(filter.column) && filter.column && (
                            <option value={filter.column}>{filter.column}</option>
                          )}
                          {allFields.map((col) => (
                            <option key={col} value={col}>{formatFieldLabel(col)}</option>
                          ))}
                        </select>
                      </div>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFilter(filter.id)}
                        className="text-red-600 hover:text-red-700 mt-7"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>

                    <div className="text-xs text-gray-500">
                      Type: <span className="font-semibold text-gray-700">{kind}</span>
                    </div>

                    {kind === 'numeric' ? (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                          <Label>Min</Label>
                          <Input
                            type="number"
                            value={filter.min ?? ''}
                            onChange={(e) => updateNumericFilter(filter.id, 'min', e.target.value)}
                            placeholder="Valeur min"
                            className="mt-2"
                          />
                        </div>
                        <div>
                          <Label>Max</Label>
                          <Input
                            type="number"
                            value={filter.max ?? ''}
                            onChange={(e) => updateNumericFilter(filter.id, 'max', e.target.value)}
                            placeholder="Valeur max"
                            className="mt-2"
                          />
                        </div>
                      </div>
                    ) : (
                      <div>
                        <Label>Valeurs</Label>
                        {filter.column && availableModalities.length > 0 && (
                          <div className="mt-2">
                            <MultiSelect
                              options={availableModalities.map((modality) => ({
                                value: modality,
                                label: modality,
                              }))}
                              selected={filter.values ?? []}
                              onChange={(values) => updateCategoricalValues(filter.id, values)}
                              placeholder="Sélectionner les valeurs..."
                            />
                          </div>
                        )}
                        {filter.column && availableModalities.length === 0 && (
                          <p className="text-sm text-gray-500 italic mt-2">
                            Aucune valeur disponible pour cette colonne
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {filters.length === 0 && (
                <p className="text-sm text-gray-500 text-center py-4">
                  Aucun filtre. Cliquez sur "Ajouter un filtre" pour commencer.
                </p>
              )}
            </div>
            </div>
          ) : (
            <div className="space-y-4">
              {isFileModeDisabled ? (
                <div className="text-sm text-gray-600 bg-amber-50 border border-amber-200 rounded-lg p-3">
                  La creation par fichier est temporairement desactivee.
                </div>
              ) : (
                <>
                  <div>
                    <Label htmlFor="file-upload" className="mb-2">
                      Fichier de donnees
                    </Label>
                    <FileUpload
                      onFileSelect={handleFileSelect}
                      selectedFile={selectedFile}
                      accept=".csv,.xlsx"
                      maxSize={10 * 1024 * 1024}
                      error={fileError}
                      disabled={createFileMutation.isPending}
                    />
                  </div>
                  <div className="text-sm text-gray-600 bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <strong>Formats acceptes:</strong> CSV, Excel (XLSX)
                    <br />
                    <strong>Taille maximum:</strong> 10 MB
                  </div>
                </>
              )}
            </div>
          )}

          <div className="flex items-center justify-end gap-4 pt-6 border-t">
            <Button
              variant="outline"
              onClick={() => navigate('/cibles')}
            >
              Annuler
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={createMutation.isPending || createFileMutation.isPending}
              className="bg-slate-900 text-white hover:bg-slate-800"
            >
              {(createMutation.isPending || createFileMutation.isPending)
                ? (isEditing ? 'Mise a jour...' : 'Creation...')
                : (isEditing ? 'Mettre a jour' : 'Creer la cible')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
