import { Database, Edit2, Save, X, RefreshCw } from 'lucide-react';
import { useHistoriqueData, useTableColumns } from './useHistoriqueData';
import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dataApi } from '@/lib/api/definitions/data.api';
import { getApiClient } from '@/lib/api/api-client';
import Toast from '../../components/Toast';
import LoadingSpinner from '../../components/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface CategoricalFilter {
  categorical?: string[];
}

interface NumericFilter {
  numeric?: { min?: number; max?: number };
}

interface FilterConfig {
  [column: string]: CategoricalFilter | NumericFilter;
}

interface EditingCell {
  rowid: number;
  col: string;
  value: string | number;
}

export default function HistoriquePage() {
  const apiClient = getApiClient();
  const queryClient = useQueryClient();
  const { tables, isLoading: tablesLoading } = useHistoriqueData();
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterConfig>({});
  const [debouncedFilters, setDebouncedFilters] = useState<FilterConfig>({});
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
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

  // Fetch table data
  const { data: tableData, isLoading: dataLoading } = useQuery<{ rows: any[]; total?: number; count?: number }>({
    queryKey: ['table-data', selectedTable, debouncedFilters, page, pageSize],
    queryFn: () =>
      apiClient.request(
        dataApi.readTableData({
          table: selectedTable!,
          filters: debouncedFilters,
          limit: pageSize,
          offset: page * pageSize,
        })
      ),
    enabled: !!selectedTable,
  });

  // Update cell mutation
  const updateCellMutation = useMutation({
    mutationFn: (data: EditingCell) => apiClient.request(dataApi.updateCell({ table: selectedTable!, ...data })),
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

  const handleTableSelect = (tableName: string) => {
    setSelectedTable(tableName);
    setFilters({});
    setDebouncedFilters({});
    setPage(0);
  };

  const handleCellEdit = (rowid: number, col: string, currentValue: any) => {
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

  const handleFilterChange = (column: string, filterType: 'categorical' | 'numeric', value: any) => {
    setFilters((prev) => ({
      ...prev,
      [column]: filterType === 'categorical' ? { categorical: value } : { numeric: value },
    }));
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
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8 max-w-full overflow-x-hidden">
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />

      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 sm:p-3 bg-blue-100 rounded-xl">
              <Database className="w-5 h-5 sm:w-6 sm:h-6 text-blue-600" />
            </div>
            <div>
              <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">Données</h1>
              <p className="text-gray-600 text-sm sm:text-base">Consulter et modifier les données</p>
            </div>
          </div>
          {selectedTable && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => queryClient.invalidateQueries({ queryKey: ['table-data', selectedTable] })}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Actualiser
            </Button>
          )}
        </div>
      </div>

      {/* Table Selection - Compact Dropdown */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-6">
        <div className="flex items-center gap-4">
          <label className="text-sm font-medium text-gray-700 whitespace-nowrap">Table:</label>
          {tablesLoading ? (
            <LoadingSpinner size="sm" />
          ) : (
            <select
              value={selectedTable || ''}
              onChange={(e) => handleTableSelect(e.target.value)}
              className="flex-1 max-w-md px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Sélectionner une table...</option>
              {tables.map((table) => (
                <option key={table.name} value={table.name}>
                  {table.display_name || table.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Data Table */}
      {selectedTable && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="p-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-lg font-bold text-gray-900">
              {tables.find((t) => t.name === selectedTable)?.display_name || selectedTable}
            </h2>
            {Object.keys(filters).length > 0 && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="w-4 h-4 mr-2" />
                Effacer les filtres ({Object.keys(filters).length})
              </Button>
            )}
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
                      {columns.map((column) => {
                        const currentFilter = filters[column.name];
                        const numericFilter = currentFilter as NumericFilter | undefined;
                        const categoricalFilter = currentFilter as CategoricalFilter | undefined;
                        const isNumeric = column.type === 'INTEGER' || column.type === 'REAL';
                        return (
                          <th key={`${column.name}-filter`} className="py-2 px-4 align-top">
                            {isNumeric ? (
                              <div className="flex flex-col gap-2">
                                <Input
                                  type="number"
                                  placeholder="Min"
                                  value={numericFilter?.numeric?.min ?? ''}
                                  onChange={(e) => {
                                    const minValue = e.target.value ? parseFloat(e.target.value) : undefined;
                                    const maxValue = numericFilter?.numeric?.max;
                                    if (minValue === undefined && maxValue === undefined) {
                                      const nextFilters = { ...filters };
                                      delete nextFilters[column.name];
                                      setFilters(nextFilters);
                                      setPage(0);
                                      return;
                                    }
                                    handleFilterChange(column.name, 'numeric', { min: minValue, max: maxValue });
                                  }}
                                  className="h-8 text-xs"
                                />
                                <Input
                                  type="number"
                                  placeholder="Max"
                                  value={numericFilter?.numeric?.max ?? ''}
                                  onChange={(e) => {
                                    const maxValue = e.target.value ? parseFloat(e.target.value) : undefined;
                                    const minValue = numericFilter?.numeric?.min;
                                    if (minValue === undefined && maxValue === undefined) {
                                      const nextFilters = { ...filters };
                                      delete nextFilters[column.name];
                                      setFilters(nextFilters);
                                      setPage(0);
                                      return;
                                    }
                                    handleFilterChange(column.name, 'numeric', { min: minValue, max: maxValue });
                                  }}
                                  className="h-8 text-xs"
                                />
                              </div>
                            ) : (
                              <Input
                                type="text"
                                placeholder="Filtrer..."
                                value={categoricalFilter?.categorical?.[0] ?? ''}
                                onChange={(e) => {
                                  if (e.target.value) {
                                    handleFilterChange(column.name, 'categorical', [e.target.value]);
                                  } else {
                                    const nextFilters = { ...filters };
                                    delete nextFilters[column.name];
                                    setFilters(nextFilters);
                                    setPage(0);
                                  }
                                }}
                                className="h-8 text-xs"
                              />
                            )}
                          </th>
                        );
                      })}
                    </tr>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase">Actions</th>
                      {columns.map((column) => (
                        <th key={column.name} className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase whitespace-nowrap">
                          {column.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 ? (
                      <tr>
                        <td colSpan={columns.length + 1} className="py-10 text-center text-sm text-gray-500">
                          Aucune donnée disponible
                        </td>
                      </tr>
                    ) : (
                      rows.map((row, rowIndex) => (
                      <tr key={rowIndex} className={`border-b border-gray-100 ${rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}>
                        <td className="py-2 px-4">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCellEdit(row.rowid, columns[0].name, row[columns[0].name])}
                          >
                            <Edit2 className="w-4 h-4" />
                          </Button>
                        </td>
                        {columns.map((column) => (
                          <td key={column.name} className="py-2 px-4 text-sm text-gray-900 whitespace-nowrap">
                            {editingCell && editingCell.rowid === row.rowid && editingCell.col === column.name ? (
                              <div className="flex items-center gap-2">
                                <Input
                                  value={editingCell.value}
                                  onChange={(e) =>
                                    setEditingCell({ ...editingCell, value: e.target.value })
                                  }
                                  className="w-full"
                                  autoFocus
                                />
                                <Button
                                  size="sm"
                                  onClick={handleCellSave}
                                  disabled={updateCellMutation.isPending}
                                >
                                  <Save className="w-4 h-4" />
                                </Button>
                                <Button variant="ghost" size="sm" onClick={handleCellCancel}>
                                  <X className="w-4 h-4" />
                                </Button>
                              </div>
                            ) : (
                              <div
                                className="cursor-pointer hover:bg-blue-50 px-2 py-1 rounded"
                                onClick={() => handleCellEdit(row.rowid, column.name, row[column.name])}
                              >
                                {row[column.name] !== null && row[column.name] !== undefined ? String(row[column.name]) : '-'}
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
                    disabled={rows.length < pageSize}
                  >
                    Suivant
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
