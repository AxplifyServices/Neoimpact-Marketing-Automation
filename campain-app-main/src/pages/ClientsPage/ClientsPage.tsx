import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Edit2, Save, X, RefreshCw } from 'lucide-react';
import { keepPreviousData, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dataApi } from '@/lib/api/definitions/data.api';
import { getApiClient } from '@/lib/api/api-client';
import Toast from '../../components/Toast';
import LoadingSpinner from '../../components/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { TableColumnFilter, type TableColumnFilterValue } from '@/components/data-table/table-column-filter';
import { useTableColumns, useTableFilterOptions } from '../HistoriquePage/useHistoriqueData';

type FilterConfig = Record<string, TableColumnFilterValue>;

interface EditingCell {
  rowid: number;
  col: string;
  value: string | number;
}

const CLIENT_READ_ONLY_COLUMNS = new Set(['Segment_actuel', 'Risque_attrition', 'Engagement_digital', 'Creneau_connexion', 'Canal_top1', 'Canal_top2', 'Canal_top3', 'Pression_commerciale', 'Appetence_carte', 'Appetence_conso', 'Appetence_immo', 'Appetence_epargne', 'Carte_recommandee', 'Next_best_product', 'Next_best_product_score']);

const CLIENT_PRIMARY_COLUMNS = [
  'ID_Client',
  'Nom',
  'Prenom',
  'Numero_Tel',
  'Mail',
  'Region',
  'Agence',
  'Gestionnaire',
  'Segment_actuel',
  'Risque_attrition',
  'STATUT_CLIENT',
];

export default function ClientsPage() {
  const navigate = useNavigate();
  const apiClient = getApiClient();
  const queryClient = useQueryClient();
  const selectedTable = 'clients';

  const [filters, setFilters] = useState<FilterConfig>({});
  const [debouncedFilters, setDebouncedFilters] = useState<FilterConfig>({});
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [showAllColumns, setShowAllColumns] = useState(false);
  const [toast, setToast] = useState<{
    isOpen: boolean;
    title: string;
    message?: string;
    type?: 'success' | 'error' | 'warning';
  }>({
    isOpen: false,
    title: '',
  });

  const { columns, isLoading: columnsLoading } = useTableColumns(selectedTable);
  const primaryColumns = CLIENT_PRIMARY_COLUMNS
    .map((name) => columns.find((column) => column.name === name))
    .filter((column): column is (typeof columns)[number] => Boolean(column));
  const visibleColumns = showAllColumns
    ? columns
    : (primaryColumns.length ? primaryColumns : columns.slice(0, 10));
  const visibleColumnNames = visibleColumns.map((column) => column.name);
  const { filterOptions } = useTableFilterOptions(selectedTable, visibleColumnNames);

  const { data: tableData, isLoading: dataLoading } = useQuery<{ rows: any[]; total?: number; count?: number }>({
    queryKey: ['table-data', selectedTable, debouncedFilters, page, pageSize, visibleColumnNames],
    queryFn: () =>
      apiClient.request(
        dataApi.readTableData({
          table: selectedTable,
          filters: debouncedFilters,
          columns: visibleColumnNames,
          limit: pageSize,
          offset: page,
        })
      ),
    enabled: !!selectedTable,
    placeholderData: keepPreviousData,
  });

  const updateCellMutation = useMutation({
    mutationFn: (data: EditingCell) => apiClient.request(dataApi.updateCell({ table: selectedTable, ...data })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['table-data', selectedTable] });
      setToast({
        isOpen: true,
        title: 'Succès',
        message: 'Cellule mise à jour avec succès',
        type: 'success',
      });
      setEditingCell(null);
    },
    onError: () => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Impossible de mettre à jour la cellule',
        type: 'error',
      });
    },
  });

  const handleCellEdit = (rowid: number, col: string, currentValue: any) => {
    if (CLIENT_READ_ONLY_COLUMNS.has(col)) return;
    setEditingCell({ rowid, col, value: currentValue });
  };

  const handleCellSave = () => {
    if (editingCell) {
      updateCellMutation.mutate(editingCell);
    }
  };

  const handleCellCancel = () => {
    setEditingCell(null);
  };

  const handleFilterChange = (column: string, value?: TableColumnFilterValue) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (value) next[column] = value;
      else delete next[column];
      return next;
    });
    setPage(0);
  };

  const clearFilters = () => {
    setFilters({});
    setDebouncedFilters({});
    setPage(0);
  };

  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedFilters(filters);
    }, 350);

    return () => clearTimeout(timeout);
  }, [filters]);

  const rows = tableData?.rows || [];
  const total = tableData?.total || tableData?.count || rows.length;
  const totalPages = total > 0 ? Math.ceil(total / pageSize) : 1;

  return (
    <div className="min-h-screen bg-gray-50 p-3 sm:p-4 lg:p-6 pt-16 lg:pt-6">
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">Clients</h1>
            <p className="text-gray-600 text-xs sm:text-sm">Gérez vos clients et leurs informations</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => queryClient.invalidateQueries({ queryKey: ['table-data', selectedTable] })}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Actualiser
            </Button>
            <Button
              onClick={() => navigate('/clients/create')}
              className="bg-slate-900 text-white hover:bg-slate-800"
            >
              <Plus className="w-4 h-4 mr-2" />
              Nouveau client
            </Button>
          </div>
        </div>

        {/* Data Table */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="p-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-lg font-bold text-gray-900">Clients</h2>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowAllColumns((value) => !value);
                  clearFilters();
                }}
              >
                {showAllColumns ? 'Colonnes essentielles' : `Toutes les colonnes (${columns.length})`}
              </Button>
            {Object.keys(filters).length > 0 && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="w-4 h-4 mr-2" />
                Effacer les filtres ({Object.keys(filters).length})
              </Button>
            )}
            </div>
          </div>

          {dataLoading || columnsLoading ? (
            <div className="flex items-center justify-center py-20">
              <LoadingSpinner size="lg" />
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr className="border-b border-gray-200">
                      <th className="py-2 px-4" />
                      {visibleColumns.map((column) => (
                        <th key={`${column.name}-filter`} className="py-2 px-4 align-top">
                          <TableColumnFilter
                            columnName={column.name}
                            meta={filterOptions[column.name]}
                            value={filters[column.name]}
                            onChange={(value) => handleFilterChange(column.name, value)}
                          />
                        </th>
                      ))}
                    </tr>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase">Actions</th>
                      {visibleColumns.map((column) => (
                        <th
                          key={column.name}
                          className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase whitespace-nowrap"
                        >
                          {column.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 ? (
                      <tr>
                        <td colSpan={visibleColumns.length + 1} className="py-10 text-center text-sm text-gray-500">
                          Aucune donnée disponible
                        </td>
                      </tr>
                    ) : (
                      rows.map((row, rowIndex) => (
                        <tr
                          key={rowIndex}
                          className={`border-b border-gray-100 ${rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}
                        >
                          <td className="py-2 px-4">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCellEdit(Number(row.__rowid__ ?? row.rowid), visibleColumns[0].name, row[visibleColumns[0].name])}
                            >
                              <Edit2 className="w-4 h-4" />
                            </Button>
                          </td>
                          {visibleColumns.map((column) => (
                            <td key={column.name} className="py-2 px-4 text-sm text-gray-900 whitespace-nowrap">
                              {editingCell && editingCell.rowid === Number(row.__rowid__ ?? row.rowid) && editingCell.col === column.name ? (
                                <div className="flex items-center gap-2">
                                  <Input
                                    value={editingCell.value}
                                    onChange={(e) => setEditingCell({ ...editingCell, value: e.target.value })}
                                    className="w-full"
                                    autoFocus
                                  />
                                  <Button size="sm" onClick={handleCellSave} disabled={updateCellMutation.isPending}>
                                    <Save className="w-4 h-4" />
                                  </Button>
                                  <Button variant="ghost" size="sm" onClick={handleCellCancel}>
                                    <X className="w-4 h-4" />
                                  </Button>
                                </div>
                              ) : (
                                <div
                                  className={`${CLIENT_READ_ONLY_COLUMNS.has(column.name) ? 'cursor-default' : 'cursor-pointer hover:bg-blue-50'} px-2 py-1 rounded`}
                                  onClick={() => handleCellEdit(Number(row.__rowid__ ?? row.rowid), column.name, row[column.name])}
                                >
                                  {row[column.name] !== null && row[column.name] !== undefined
                                    ? String(row[column.name])
                                    : '-'}
                                </div>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="p-4 border-t border-gray-200 flex items-center justify-between">
                <div className="text-sm text-gray-600">
                  {total > 0 ? (
                    <>
                      Affichage de {page * pageSize + 1} à {Math.min((page + 1) * pageSize, total)}
                      {tableData?.total !== undefined && ` sur ${total} résultats`}
                    </>
                  ) : (
                    'Aucun résultat'
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2 text-sm text-gray-600">
                    <span>Lignes par page</span>
                    <select
                      value={pageSize}
                      onChange={(e) => {
                        setPageSize(Number(e.target.value));
                        setPage(0);
                      }}
                      className="h-8 rounded-md border border-gray-300 bg-white px-2 text-sm"
                    >
                      {[10, 25, 50, 100].map((size) => (
                        <option key={size} value={size}>
                          {size}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                  >
                    Précédent
                  </Button>
                  <span className="text-sm text-gray-600">
                    Page {page + 1}{tableData?.total !== undefined && ` / ${totalPages}`}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => p + 1)}
                    disabled={page + 1 >= totalPages}
                  >
                    Suivant
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
