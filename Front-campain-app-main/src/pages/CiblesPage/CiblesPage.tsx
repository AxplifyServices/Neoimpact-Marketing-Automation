import { Database, FileText, Calendar, MoreVertical, Edit, Trash2, Eye, Plus, Lock, Copy } from 'lucide-react';
import { useCiblesData } from './useCiblesData';
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ciblesApi } from '@/lib/api/definitions/cibles.api';
import { getApiClient } from '@/lib/api/api-client';
import Toast from '../../components/Toast';
import ConfirmDialog from '../../components/ConfirmDialog';
import { type ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table/data-table';
import { DataTableToolbar } from '@/components/data-table/toolbar';
import { DataTablePagination } from '@/components/data-table/pagination';
import { DataTableColumnHeader } from '@/components/data-table/column-header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { CibleData } from './useCiblesData';

export default function CiblesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const apiClient = getApiClient();
  const { stats: statsData, cibles, isLoading, lockedCibles } = useCiblesData();
  const [toast, setToast] = useState<{
    isOpen: boolean;
    title: string;
    message?: string;
    type?: 'success' | 'error' | 'warning';
  }>({
    isOpen: false,
    title: '',
  });
  const [deleteDialog, setDeleteDialog] = useState<{
    isOpen: boolean;
    cibleId?: string;
    cibleName?: string;
  }>({
    isOpen: false,
  });
  const [dateMin, setDateMin] = useState<string>('');
  const [dateMax, setDateMax] = useState<string>('');
  const usedCount = lockedCibles.length;
  const unusedCount = Math.max(cibles.length - usedCount, 0);
  const usagePercent = cibles.length > 0 ? Math.round((usedCount / cibles.length) * 100) : 0;
  const dbCount = cibles.filter(c => c.source?.toLowerCase() === 'db').length;
  const fileCount = cibles.filter(c => c.source?.toLowerCase() === 'file').length;
  const sourceTotal = dbCount + fileCount;
  const dbPercent = sourceTotal > 0 ? Math.round((dbCount / sourceTotal) * 100) : 0;
  const filePercent = sourceTotal > 0 ? Math.round((fileCount / sourceTotal) * 100) : 0;

  // Delete cible mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.request(ciblesApi.delete(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cibles'] });
      setToast({
        isOpen: true,
        title: 'Succès',
        message: `La cible "${deleteDialog.cibleName}" a été supprimée avec succès`,
        type: 'success',
      });
      setDeleteDialog({ isOpen: false });
    },
    onError: () => {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Une erreur est survenue lors de la suppression',
        type: 'error',
      });
    },
  });

  const handleNewCible = () => {
    navigate('/cibles/create');
  };

  const handleViewCible = (cibleId: string) => {
    navigate(`/cibles/${cibleId}/view`);
  };

  const handleEditCible = (cibleId: string) => {
    const isLocked = lockedCibles.includes(cibleId);

    if (isLocked) {
      setToast({
        isOpen: true,
        title: 'Cible utilisée',
        message: 'Cette cible est actuellement utilisée dans une campagne active et ne peut pas être modifiée',
        type: 'warning',
      });
      return;
    }

    navigate(`/cibles/${cibleId}/edit`);
  };

  const handleDuplicateCible = (cible: CibleData) => {
    navigate('/cibles/create', { state: { duplicateId: cible.id_cible } });
  };

  const handleDeleteCible = (cibleId: string, cibleName: string) => {
    const isLocked = lockedCibles.includes(cibleId);

    if (isLocked) {
      setToast({
        isOpen: true,
        title: 'Cible utilisée',
        message: 'Cette cible est actuellement utilisée dans une campagne active et ne peut pas être supprimée',
        type: 'warning',
      });
      return;
    }

    setDeleteDialog({
      isOpen: true,
      cibleId,
      cibleName,
    });
  };

  const confirmDelete = () => {
    if (deleteDialog.cibleId) {
      deleteMutation.mutate(deleteDialog.cibleId);
    }
  };

  // Define columns for TanStack Table
  const columns = useMemo<ColumnDef<CibleData>[]>(
    () => [
      {
        accessorKey: 'nom_cible',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Nom de la cible" />,
        cell: ({ row }) => {
          const isLocked = row.original.locked === true;
          const lockReason = row.original.lock_reason;
          return (
            <div className="flex items-start gap-2">
              <div className="flex flex-col flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-gray-900 text-sm">{row.original.nom_cible}</span>
                  {isLocked && (
                    <span
                      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200"
                      title={lockReason || 'En cours d\'utilisation'}
                    >
                      <Lock className="w-3 h-3 mr-1" />
                      En cours
                    </span>
                  )}
                </div>
                <span className="text-xs text-gray-500 font-mono mt-1">{row.original.id_cible}</span>
                {isLocked && lockReason && (
                  <span className="text-xs text-amber-700 mt-1">{lockReason}</span>
                )}
              </div>
            </div>
          );
        },
        filterFn: (row, id, value) => {
          return row.getValue<string>(id)?.toLowerCase().includes(value.toLowerCase()) ?? false;
        },
      },
      {
        accessorKey: 'source',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Source" />,
        cell: ({ getValue }) => {
          const source = (getValue() as string).toLowerCase();
          return (
            <span
              className={`inline-flex items-center px-3 py-1.5 rounded-full text-xs font-semibold ${
                source === 'db'
                  ? 'bg-blue-100 text-blue-700 border border-blue-200'
                  : 'bg-purple-100 text-purple-700 border border-purple-200'
              }`}
            >
              {source === 'db' ? (
                <>
                  <Database className="w-3 h-3 mr-1" />
                  Database
                </>
              ) : (
                <>
                  <FileText className="w-3 h-3 mr-1" />
                  Fichier
                </>
              )}
            </span>
          );
        },
        filterFn: (row, id, value) => {
          return value.includes(row.getValue(id));
        },
      },
      {
        accessorKey: 'date_creation',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Date de création" />,
        cell: ({ getValue }) => (
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-400" />
            <span className="text-sm text-gray-700 font-medium">
              {new Date(getValue() as string).toLocaleDateString('fr-FR', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
              })}
            </span>
          </div>
        ),
        filterFn: (row, id, value) => {
          const dateStr = row.getValue(id) as string;
          const date = new Date(dateStr);
          const { min, max } = value as { min?: string; max?: string };

          if (min && max) {
            return date >= new Date(min) && date <= new Date(max);
          } else if (min) {
            return date >= new Date(min);
          } else if (max) {
            return date <= new Date(max);
          }
          return true;
        },
      },
      {
        accessorKey: 'locked',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Statut" />,
        cell: ({ row }) => {
          const isLocked = row.original.locked === true;
          return (
            <span
              className={`inline-flex items-center px-3 py-1.5 rounded-full text-xs font-semibold ${
                isLocked
                  ? 'bg-amber-100 text-amber-700 border border-amber-200'
                  : 'bg-green-100 text-green-700 border border-green-200'
              }`}
            >
              {isLocked ? (
                <>
                  <Lock className="w-3 h-3 mr-1" />
                  Utilisée
                </>
              ) : (
                'Disponible'
              )}
            </span>
          );
        },
        filterFn: (row, id, value) => {
          return value.includes(row.getValue(id) ? 'locked' : 'available');
        },
      },
      {
        id: 'actions',
        header: () => <div className="text-center">Actions</div>,
        cell: ({ row }) => {
          const isLocked = lockedCibles.includes(row.original.id_cible);
          return (
            <div className="flex items-center justify-center">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="h-8 w-8 p-0">
                    <span className="sr-only">Ouvrir le menu</span>
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => handleViewCible(row.original.id_cible)}>
                    <Eye className="mr-2 h-4 w-4" />
                    <span>Voir détails</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => handleEditCible(row.original.id_cible)}
                    disabled={isLocked}
                    className={isLocked ? 'opacity-50 cursor-not-allowed' : ''}
                  >
                    <Edit className="mr-2 h-4 w-4" />
                    <span>Modifier</span>
                    {isLocked && <Lock className="ml-auto h-3 w-3" />}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleDuplicateCible(row.original)}>
                    <Copy className="mr-2 h-4 w-4" />
                    <span>Dupliquer</span>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() => handleDeleteCible(row.original.id_cible, row.original.nom_cible)}
                    disabled={isLocked}
                    className={isLocked ? 'opacity-50 cursor-not-allowed' : 'text-red-600'}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    <span>Supprimer</span>
                    {isLocked && <Lock className="ml-auto h-3 w-3" />}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        },
      },
    ],
    [lockedCibles]
  );

  // Filter options for source
  const sourceFilterOptions = useMemo(() => [
    {
      label: 'Database',
      value: 'db',
      icon: Database,
    },
    {
      label: 'Fichier',
      value: 'file',
      icon: FileText,
    },
  ], []);

  // Filter options for status
  const statusFilterOptions = useMemo(() => [
    {
      label: 'Disponible',
      value: 'available',
    },
    {
      label: 'Utilisée',
      value: 'locked',
      icon: Lock,
    },
  ], []);

  const stats = [
    {
      icon: <Database className="w-5 h-5 text-blue-600" />,
      ...statsData[0],
    },
    {
      icon: <Database className="w-5 h-5 text-purple-600" />,
      ...statsData[1],
    },
    {
      icon: <FileText className="w-5 h-5 text-green-600" />,
      ...statsData[2],
    },
  ];
  const totalStat = stats[0];

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
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-2">Cibles</h1>
          <p className="text-gray-600 text-sm sm:text-base">
            Gérez vos cibles de campagne (bases de données et fichiers)
          </p>
        </div>
        <button
          type="button"
          onClick={handleNewCible}
          className="bg-slate-900 text-white px-6 py-3 rounded-xl font-medium hover:bg-slate-800 transition-colors flex items-center gap-2 cursor-pointer whitespace-nowrap"
        >
          <Plus className="w-5 h-5" />
          Nouvelle cible
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {totalStat && (
          <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100">
            <div className="flex items-start justify-between mb-4">
              <div className="p-2 bg-gray-50 rounded-lg">{totalStat.icon}</div>
              <span className={`text-sm font-semibold ${totalStat.changeColor}`}>{totalStat.change}</span>
            </div>
            <div className="text-3xl font-bold text-gray-900 mb-1">{totalStat.value}</div>
            <div className="text-sm text-gray-600">{totalStat.label}</div>
          </div>
        )}

        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="p-2 bg-gray-50 rounded-lg">
                <Database className="w-5 h-5 text-blue-600" />
              </div>
              <div className="p-2 bg-gray-50 rounded-lg">
                <FileText className="w-5 h-5 text-purple-600" />
              </div>
            </div>
            <span className="text-sm font-semibold text-gray-600">Sources</span>
          </div>
          <div className="space-y-4">
            <div className="text-xs text-gray-500">
              {sourceTotal} source{sourceTotal > 1 ? 's' : ''}
            </div>

            <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
              <div className="h-2 bg-blue-500" style={{ width: `${dbPercent}%` }} />
              <div className="h-2 bg-purple-500" style={{ width: `${filePercent}%` }} />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center justify-between rounded-lg border border-blue-100 bg-blue-50 px-3 py-2">
                <div>
                  <div className="text-xs font-semibold text-blue-700">Cibles DB</div>
                  <div className="text-[11px] text-blue-600">Basees sur filtres</div>
                </div>
                <div className="text-lg font-bold text-blue-700">{dbCount}</div>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-purple-100 bg-purple-50 px-3 py-2">
                <div>
                  <div className="text-xs font-semibold text-purple-700">Cibles fichier</div>
                  <div className="text-[11px] text-purple-600">Importees</div>
                </div>
                <div className="text-lg font-bold text-purple-700">{fileCount}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Usage Card */}
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-start justify-between mb-4">
            <div className="p-2 bg-gray-50 rounded-lg">
              <Lock className="w-5 h-5 text-amber-600" />
            </div>
            <span className="text-sm font-semibold text-gray-600">Utilisation</span>
          </div>

          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-700">En cours</span>
              <span className="text-sm font-semibold text-amber-700">{usedCount}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 mb-3">
              <div
                className="bg-amber-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${cibles.length > 0 ? (usedCount / cibles.length) * 100 : 0}%` }}
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Disponibles</span>
              <span className="text-sm font-semibold text-green-700">{unusedCount}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-green-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${cibles.length > 0 ? (unusedCount / cibles.length) * 100 : 0}%` }}
              />
            </div>
          </div>

          <div className="text-center pt-2 border-t border-gray-100">
            <span className="text-2xl font-bold text-gray-900">{usagePercent}%</span>
            <span className="text-sm text-gray-600 ml-1">en utilisation</span>
          </div>
        </div>
      </div>

      {/* Data Table */}
      <DataTable
        columns={columns}
        data={cibles}
        isLoading={isLoading}
        toolbar={(table) => (
          <DataTableToolbar
            table={table}
            searchPlaceholder="Rechercher une cible..."
            searchKey="nom_cible"
            filters={[
              {
                columnId: 'source',
                title: 'Source',
                options: sourceFilterOptions,
              },
              {
                columnId: 'locked',
                title: 'Statut',
                options: statusFilterOptions,
              },
            ]}
            onReset={() => {
              setDateMin('');
              setDateMax('');
            }}
          >
            {/* Date range filter */}
            <Input
              type="date"
              value={dateMin}
              onChange={(e) => {
                const newDateMin = e.target.value;
                setDateMin(newDateMin);
                if (newDateMin || dateMax) {
                  table.getColumn('date_creation')?.setFilterValue({ min: newDateMin, max: dateMax });
                } else {
                  table.getColumn('date_creation')?.setFilterValue(undefined);
                }
              }}
              max={dateMax || undefined}
              placeholder="Date début"
              className="h-8 w-[150px]"
            />
            <Input
              type="date"
              value={dateMax}
              onChange={(e) => {
                const newDateMax = e.target.value;
                setDateMax(newDateMax);
                if (dateMin || newDateMax) {
                  table.getColumn('date_creation')?.setFilterValue({ min: dateMin, max: newDateMax });
                } else {
                  table.getColumn('date_creation')?.setFilterValue(undefined);
                }
              }}
              min={dateMin || undefined}
              placeholder="Date fin"
              className="h-8 w-[150px]"
            />
          </DataTableToolbar>
        )}
        paginationComponent={(table, callbacks) => (
          <DataTablePagination table={table} {...callbacks} />
        )}
      />
    </div>
  );
}
