import { Target, Calendar, Database, MoreVertical, Edit, Trash2, Eye, Lock, Copy } from 'lucide-react';
import { useModelesData } from './useModelesData';
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Toast from '../../components/Toast';
import ConfirmDialog from '../../components/ConfirmDialog';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { getApiClient } from '@/lib/api/api-client';
import { type ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table/data-table';
import { DataTableToolbar } from '@/components/data-table/toolbar';
import { DataTablePagination } from '@/components/data-table/pagination';
import { DataTableColumnHeader } from '@/components/data-table/column-header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { parseObjectif, type ParsedObjectifItem } from '@/lib/utils';

interface ModeleData {
  id_modele: string;
  nom_modele: string;
  variable_cible: string;
  objectif: string;
  date_creation: string;
}

const renderItemBadge = (item: ParsedObjectifItem, showVariable = false) => {
  const label = showVariable && item.variable ? `${item.variable}: ${item.label}` : item.label;

  if (item.type === 'num') {
    return (
      <span className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-semibold bg-sky-100 text-sky-700 border border-sky-200">
        {label}
      </span>
    );
  }

  const isActive = item.label === 'Actif';
  return (
    <span
      className={`inline-flex items-center px-3 py-1.5 rounded-full text-xs font-semibold border ${
        isActive ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-100 text-gray-700 border-gray-200'
      }`}
      title={label}
    >
      <span className={`w-1.5 h-1.5 rounded-full mr-2 ${isActive ? 'bg-green-500' : 'bg-gray-500'}`} />
      {label}
    </span>
  );
};

const renderObjectifBadge = (objectif: string) => {
  const parsed = parseObjectif(objectif);

  if (parsed.kind === 'empty') {
    return <span className="text-xs text-gray-400">Non défini</span>;
  }

  if (parsed.kind === 'single') {
    return renderItemBadge(parsed.item);
  }

  // Multi-objectif - compact badge with hover tooltip
  const opLabel = parsed.op === 'AND' ? 'ET' : 'OU';
  const tooltipText = parsed.items
    .map(item => `${item.variable}: ${item.label}`)
    .join(` ${opLabel} `);

  return (
    <span
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-violet-100 text-violet-700 border border-violet-200 cursor-help"
      title={tooltipText}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-violet-500" />
      {parsed.items.length} objectifs ({opLabel})
    </span>
  );
};

export default function ModelesPage() {
  const navigate = useNavigate();
  const { stats: statsData, modeles, isLoading, refetch, lockedModels, usedCount, unusedCount } = useModelesData();
  const apiClient = getApiClient();
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' | 'warning' }>({
    isOpen: false,
    title: '',
  });
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [dateMin, setDateMin] = useState<string>('');
  const [dateMax, setDateMax] = useState<string>('');

  const handleNewModele = () => {
    navigate('/modeles/create');
  };

  const handleViewModele = (modeleId: string) => {
    navigate(`/modeles/${modeleId}/view`);
  };

  const handleEditModele = (modeleId: string) => {
    const isLocked = lockedModels.includes(modeleId);

    if (isLocked) {
      setToast({
        isOpen: true,
        title: 'Modèle utilisé',
        message: 'Ce modèle est actuellement utilisé dans une campagne active et ne peut pas être modifié',
        type: 'warning',
      });
      return;
    }

    navigate(`/modeles/${modeleId}/edit`);
  };

  const handleDuplicateModele = (modeleId: string) => {
    navigate('/modeles/create', { state: { duplicateId: modeleId } });
  };

  const handleDeleteModele = (modeleId: string) => {
    const isLocked = lockedModels.includes(modeleId);

    if (isLocked) {
      setToast({
        isOpen: true,
        title: 'Modèle utilisé',
        message: 'Ce modèle est actuellement utilisé dans une campagne active et ne peut pas être supprimé',
        type: 'warning',
      });
      return;
    }

    setDeleteTargetId(modeleId);
  };

  const confirmDeleteModele = async () => {
    if (!deleteTargetId) {
      return;
    }

    try {
      await apiClient.request(modelesApi.delete(deleteTargetId));
      setToast({
        isOpen: true,
        title: 'Succès',
        message: 'Modèle supprimé avec succès',
        type: 'success',
      });
      refetch();
    } catch (error) {
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: 'Impossible de supprimer le modèle',
        type: 'error',
      });
    } finally {
      setDeleteTargetId(null);
    }
  };

  // Define columns for TanStack Table
  const columns = useMemo<ColumnDef<ModeleData>[]>(
    () => [
      {
        accessorKey: 'nom_modele',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Nom du modèle" />,
        cell: ({ row }) => {
          const isLocked = lockedModels.includes(row.original.id_modele);
          return (
            <div className="flex items-start gap-2">
              <div className="flex flex-col flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-gray-900 text-sm">{row.original.nom_modele}</span>
                  {isLocked && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">
                      <Lock className="w-3 h-3 mr-1" />
                      En cours
                    </span>
                  )}
                </div>
                <span className="text-xs text-gray-500 font-mono mt-1">{row.original.id_modele}</span>
              </div>
            </div>
          );
        },
        filterFn: (row, id, value) => {
          return row.getValue<string>(id)?.toLowerCase().includes(value.toLowerCase()) ?? false;
        },
      },
      {
        accessorKey: 'variable_cible',
        header: ({ column }) => <DataTableColumnHeader column={column} title="Objectif" />,
        cell: ({ row }) => {
          const parsed = parseObjectif(row.original.objectif);
          const isMulti = parsed.kind === 'multi';

          if (isMulti) {
            // Multi-objectif: badges already include variable names
            return (
              <div className="flex flex-wrap items-center gap-1">
                {renderObjectifBadge(row.original.objectif)}
              </div>
            );
          }

          // Single objectif: show variable + value
          return (
            <div className="flex items-center gap-2 whitespace-nowrap">
              <span className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-700 border border-blue-200 w-fit">
                {row.original.variable_cible}
              </span>
              {renderObjectifBadge(row.original.objectif)}
            </div>
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
          const isLocked = lockedModels.includes(row.original.id_modele);
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
                  Utilisé
                </>
              ) : (
                'Disponible'
              )}
            </span>
          );
        },
        filterFn: (row, id, value) => {
          const isLocked = lockedModels.includes(row.original.id_modele);
          return value.includes(isLocked ? 'locked' : 'available');
        },
      },
      {
        id: 'actions',
        header: () => <div className="text-center">Actions</div>,
        cell: ({ row }) => {
          const isLocked = lockedModels.includes(row.original.id_modele);
          return (
            <div className="flex items-center justify-center">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    className="h-8 w-8 p-0"
                  >
                    <span className="sr-only">Ouvrir le menu</span>
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => handleViewModele(row.original.id_modele)}>
                    <Eye className="mr-2 h-4 w-4" />
                    <span>Voir détails</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => handleEditModele(row.original.id_modele)}
                    disabled={isLocked}
                    className={isLocked ? 'opacity-50 cursor-not-allowed' : ''}
                  >
                    <Edit className="mr-2 h-4 w-4" />
                    <span>Modifier</span>
                    {isLocked && <Lock className="ml-auto h-3 w-3" />}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleDuplicateModele(row.original.id_modele)}>
                    <Copy className="mr-2 h-4 w-4" />
                    <span>Dupliquer</span>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() => handleDeleteModele(row.original.id_modele)}
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
    [lockedModels]
  );

  // Get unique variable cibles for filter
  const variableCibleOptions = useMemo(() => {
    const uniqueVariables = Array.from(new Set(modeles.map(m => m.variable_cible)));
    return uniqueVariables.map(variable => ({
      label: variable,
      value: variable,
    }));
  }, [modeles]);

  // Filter options for status
  const statusFilterOptions = useMemo(() => [
    {
      label: 'Disponible',
      value: 'available',
    },
    {
      label: 'Utilisé',
      value: 'locked',
      icon: Lock,
    },
  ], []);

  const usedPercent = modeles.length > 0 ? Math.round((usedCount / modeles.length) * 100) : 0;
  const unusedPercent = modeles.length > 0 ? Math.round((unusedCount / modeles.length) * 100) : 0;

  const stats = [
    {
      icon: <Database className="w-5 h-5 text-blue-600" />,
      ...statsData[0],
    },
    {
      icon: <Lock className="w-5 h-5 text-amber-600" />,
      value: String(usedCount),
      label: 'UtilisAc',
      change: `${usedPercent}% en utilisation`,
      changeColor: 'text-amber-600',
    },
    {
      icon: <Target className="w-5 h-5 text-green-600" />,
      value: String(unusedCount),
      label: 'Disponibles',
      change: `${unusedPercent}% disponibles`,
      changeColor: 'text-green-600',
    },
  ];

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
        isOpen={!!deleteTargetId}
        onClose={() => setDeleteTargetId(null)}
        onConfirm={confirmDeleteModele}
        title="Supprimer le modèle"
        message="Êtes-vous sûr de vouloir supprimer ce modèle ? Cette action est irréversible."
        confirmText="Supprimer"
        cancelText="Annuler"
        type="danger"
      />

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-2">Modèles</h1>
          <p className="text-gray-600 text-sm sm:text-base">Gérez vos modèles de campagne et leurs configurations</p>
        </div>
        <button
          type="button"
          onClick={handleNewModele}
          className="bg-slate-900 text-white px-6 py-3 rounded-xl font-medium hover:bg-slate-800 transition-colors flex items-center gap-2 cursor-pointer whitespace-nowrap"
        >
          <span className="text-xl">+</span>
          Nouveau modèle
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {stats.map((stat, index) => (
          <div key={index} className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100">
            <div className="flex items-start justify-between mb-4">
              <div className="p-2 bg-gray-50 rounded-lg">
                {stat.icon}
              </div>
              <span className={`text-sm font-semibold ${stat.changeColor}`}>{stat.change}</span>
            </div>
            <div className="text-3xl font-bold text-gray-900 mb-1">{stat.value}</div>
            <div className="text-sm text-gray-600">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Data Table */}
      <DataTable
        columns={columns}
        data={modeles}
        isLoading={isLoading}
        toolbar={(table) => (
          <DataTableToolbar
            table={table}
            searchPlaceholder="Rechercher un modèle..."
            searchKey="nom_modele"
            filters={[
              {
                columnId: 'variable_cible',
                title: 'Variable Cible',
                options: variableCibleOptions,
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
