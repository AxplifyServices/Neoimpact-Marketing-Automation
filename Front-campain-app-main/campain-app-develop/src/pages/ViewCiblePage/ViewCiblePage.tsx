import { ArrowLeft } from 'lucide-react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { type ColumnDef } from '@tanstack/react-table';
import { ciblesApi } from '@/lib/api/definitions/cibles.api';
import { getApiClient } from '@/lib/api/api-client';
import LoadingSpinner from '../../components/LoadingSpinner';
import { DataTable } from '@/components/data-table/data-table';
import { DataTableColumnHeader } from '@/components/data-table/column-header';
import { DataTablePagination } from '@/components/data-table/pagination';
import { Label } from '@/components/ui/label';
import type { CibleData } from '../CiblesPage/useCiblesData';

type ViewFilter = {
  id: string;
  column: string;
  kind: 'numeric' | 'categorical';
  min?: string;
  max?: string;
  values: string[];
};

export default function ViewCiblePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const apiClient = getApiClient();

  const { data: cible, isLoading } = useQuery<CibleData>({
    queryKey: ['cible', id],
    queryFn: () => apiClient.request<CibleData>(ciblesApi.findById(id!)),
    enabled: !!id,
  });

  // Parse filter if it's a string, handle both uppercase and lowercase source
  const parsedFiltre = cible?.filtre
    ? (typeof cible.filtre === 'string' ? JSON.parse(cible.filtre) : cible.filtre)
    : null;

  const isDbSource = cible?.source?.toLowerCase() === 'db';

  // Fetch filter separately if source is 'db' and filter is not in main response
  const { data: filtreData, isLoading: isLoadingFiltre } = useQuery({
    queryKey: ['cible-filtre', id],
    queryFn: () => apiClient.request<Record<string, any>>(ciblesApi.getFiltre(id!)),
    enabled: !!id && !!cible && isDbSource && !parsedFiltre,
  });

  // Use filter from main response or from separate fetch
  const displayFiltre = parsedFiltre || filtreData;

  const formatFieldLabel = (field: string) =>
    field
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/\b\w/g, (c) => c.toUpperCase());

  const filtersList = useMemo<ViewFilter[]>(() => {
    if (!displayFiltre) return [];

    return Object.entries(displayFiltre).flatMap<ViewFilter>(([column, value]) => {
      if (Array.isArray(value)) {
        return [{
          id: column,
          column,
          kind: 'categorical' as const,
          values: value.map((item) => String(item)),
        }];
      }

      if (value && typeof value === 'object') {
        const valueObj = value as Record<string, unknown>;
        if (Array.isArray((value as any).values)) {
          return [{
            id: column,
            column,
            kind: 'categorical' as const,
            values: (value as any).values.map((item: unknown) => String(item)),
          }];
        }

        if ('min' in valueObj || 'max' in valueObj) {
          const minVal = valueObj.min !== undefined ? String(valueObj.min) : '';
          const maxVal = valueObj.max !== undefined ? String(valueObj.max) : '';
          return [{
            id: column,
            column,
            kind: 'numeric' as const,
            min: minVal,
            max: maxVal,
            values: [],
          }];
        }
      }

      return [];
    });
  }, [displayFiltre]);

  // Fetch preview data (API returns all data, we handle pagination client-side)
  const { data: previewResponse, isLoading: isLoadingPreview } = useQuery({
    queryKey: ['cible-preview', id],
    queryFn: () => apiClient.request<{ rows: any[]; total: number }>(ciblesApi.preview(id!)),
    enabled: !!id,
  });

  const previewData = previewResponse?.rows || [];
  const totalRows = previewResponse?.total || 0;

  // Generate columns dynamically from preview data
  const columns = useMemo<ColumnDef<any>[]>(() => {
    if (!previewData || previewData.length === 0) return [];

    return Object.keys(previewData[0]).map((key) => ({
      accessorKey: key,
      header: ({ column }) => <DataTableColumnHeader column={column} title={key} />,
      cell: ({ row }) => {
        const value = row.getValue(key);
        return (
          <div className="text-sm">
            {value !== null && value !== undefined ? String(value) : '-'}
          </div>
        );
      },
    }));
  }, [previewData]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      </div>
    );
  }

  if (!cible) {
    return (
      <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
        <div className="max-w-7xl mx-auto">
          <button
            onClick={() => navigate('/cibles')}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
            <span>Retour aux cibles</span>
          </button>
          <div className="text-center py-12">
            <p className="text-gray-500">Cible non trouvée</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
      <div className="max-w-7xl mx-auto">
        <button
          onClick={() => navigate('/cibles')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>Retour aux cibles</span>
        </button>

        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">{cible.nom_cible}</h1>
            <p className="text-gray-600 mt-2">Détails de la cible (lecture seule)</p>
          </div>
          <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-medium">
            Lecture seule
          </span>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">ID Cible</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {cible.id_cible}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nom</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {cible.nom_cible}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Source</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {isDbSource ? 'Base de données' : 'Fichier'}
              </div>
            </div>
          </div>

          {isDbSource && (
            <>
              <div className="border-t pt-6">
                <h3 className="text-lg font-semibold mb-3">Filtres</h3>
                {isLoadingFiltre ? (
                  <p className="text-sm text-gray-500">Chargement des filtres...</p>
                ) : filtersList.length > 0 ? (
                  <div className="space-y-3">
                    {filtersList.map((filter) => (
                      <div key={filter.id} className="p-3 border rounded-md bg-gray-50">
                        <div className="grid grid-cols-1 md:grid-cols-[220px_140px_1fr] gap-3 items-center">
                          <div>
                            <Label className="text-xs">Colonne</Label>
                            <div className="mt-1 px-2 py-1.5 border rounded bg-white text-sm text-gray-700">
                              {formatFieldLabel(filter.column)}
                            </div>
                          </div>

                          <div>
                            <Label className="text-xs">Type</Label>
                            <div className="mt-1 px-2 py-1.5 border rounded bg-white text-sm text-gray-700">
                              {filter.kind === 'numeric' ? 'Numérique' : 'Catégoriel'}
                            </div>
                          </div>

                          {filter.kind === 'numeric' ? (
                            <div className="grid grid-cols-2 gap-2">
                              <div>
                                <Label className="text-xs">Min</Label>
                                <div className="mt-1 px-2 py-1.5 border rounded bg-white text-sm text-gray-700">
                                  {filter.min || '-'}
                                </div>
                              </div>
                              <div>
                                <Label className="text-xs">Max</Label>
                                <div className="mt-1 px-2 py-1.5 border rounded bg-white text-sm text-gray-700">
                                  {filter.max || '-'}
                                </div>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <Label className="text-xs">Valeurs</Label>
                              <div
                                className="mt-1 px-2 py-1.5 border rounded bg-white text-sm text-gray-700 truncate"
                                title={filter.values.join(', ')}
                              >
                                {filter.values.length > 0 ? filter.values.join(', ') : 'Aucune valeur'}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500 text-center py-4">Aucun filtre</p>
                )}
              </div>

            </>
          )}

          {!isDbSource && cible.chemin && (
            <div className="border-t pt-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">Chemin du fichier</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {cible.chemin}
              </div>
            </div>
          )}
        </div>

        {/* Preview Section */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 mt-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Aperçu des données</h3>
            <span className="text-sm text-gray-500">
              {totalRows > 0 ? `${previewData.length} sur ${totalRows.toLocaleString()} lignes` : ''}
            </span>
          </div>

          {isLoadingPreview ? (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner size="md" />
            </div>
          ) : previewData && previewData.length > 0 ? (
            <DataTable
              columns={columns}
              data={previewData}
              paginationComponent={(table, callbacks) => (
                <DataTablePagination table={table} {...callbacks} />
              )}
            />
          ) : (
            <p className="text-sm text-gray-500 text-center py-8">Aucune donnée disponible</p>
          )}
        </div>
      </div>
    </div>
  );
}
