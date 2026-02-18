import { useState, useEffect, useMemo, useCallback } from 'react';
import { X, Plus, Trash2, GitBranch } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { metaApi } from '@/lib/api/definitions/meta.api';
import { getApiClient } from '@/lib/api/api-client';
import LoadingSpinner from '../LoadingSpinner';
import Toast from '../Toast';

interface CreateModeleModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

interface Block {
  id: string;
  canal: string;
  delai: number;
  parentBlockId: string | null;  // null for root blocks
  objet?: string;       // Email subject
  contenu?: string;     // Content/message
  conditions: BlockCondition[];
}

type ConditionType = 'days_since_last' | 'flag_resultat' | 'counter' | 'campaign_field' | 'client_field';

interface BlockCondition {
  id: string;
  type: ConditionType;
  operator?: string;           // =, >, <, <=, >=
  // For days_since_last type
  daysSinceLastAction?: number;
  // For flag_resultat type
  flagResultat?: string;       // "Abouti" or "Non Abouti"
  // For counter type
  counterValue?: number;
  // For campaign_field type (e.g. NB jours depuis début campagne)
  campaignField?: string;
  campaignFieldValue?: number;
  // For client_field type (e.g. client.carte_retiree) - legacy support
  clientField?: string;
  clientFieldValue?: string;
  // Common
  nextBlockId: string | null;
}

interface CampaignConditionField {
  field: string;
  db_field: string;
  type: 'numeric';
}

interface CanauxMetadata {
  canaux: string[];
  actions_by_canal: Record<string, string>;
  resultats_by_canal: Record<string, string[]>;
  compteur_by_canal: Record<string, string>;
}

interface VariablesMetadata {
  variable_choices: string[];
  categorical_cols_allowed: string[];
  numeric_cols: string[];
}

interface ObjectifItem {
  id: string;
  variable: string;
  type: 'cat' | 'num';
  value?: string;
  min?: string;
  max?: string;
}

type ObjectifMetaResponse = Record<string, string[] | 'Numérique'>;

export default function CreateModeleModal({ isOpen, onClose, onSuccess }: CreateModeleModalProps) {
  const apiClient = getApiClient();
  const queryClient = useQueryClient();

  const [formData, setFormData] = useState({
    nom_modele: '',
  });

  // Multi-objectif state
  const [objectifOperator, setObjectifOperator] = useState<'AND' | 'OR'>('AND');
  const [objectifItems, setObjectifItems] = useState<ObjectifItem[]>([]);

  const [blocks, setBlocks] = useState<Block[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [expandedBlocks, setExpandedBlocks] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' | 'warning' }>({
    isOpen: false,
    title: '',
  });

  // Fetch canaux metadata from API
  const { data: canauxData, isLoading: canauxLoading } = useQuery<CanauxMetadata>({
    queryKey: ['meta-canaux'],
    queryFn: () => apiClient.request<CanauxMetadata>(metaApi.getCanaux()),
    enabled: isOpen,
  });

  // Fetch variables metadata from API
  const { data: variablesData, isLoading: variablesLoading } = useQuery<VariablesMetadata>({
    queryKey: ['meta-variables'],
    queryFn: () => apiClient.request<VariablesMetadata>(metaApi.getVariables()),
    enabled: isOpen,
  });

  // Fetch objectif metadata
  const { data: objectifMeta } = useQuery<ObjectifMetaResponse>({
    queryKey: ['objectif-meta'],
    queryFn: () => apiClient.request<ObjectifMetaResponse>(metaApi.getObjectifMeta()),
    enabled: isOpen,
  });

  // Fetch campaign condition fields (e.g. NB jours depuis début campagne)
  const { data: campaignConditionFields } = useQuery<{ fields: CampaignConditionField[] }>({
    queryKey: ['campaign-condition-fields'],
    queryFn: () => apiClient.request<{ fields: CampaignConditionField[] }>(metaApi.getCampaignConditionFields()),
    enabled: isOpen,
  });

  // Compute objectif variables and values
  const { objectifVariables, objectifValuesByVariable } = useMemo(() => {
    if (!objectifMeta) return { objectifVariables: [], objectifValuesByVariable: {} };
    const variables = Object.keys(objectifMeta);
    return { objectifVariables: variables, objectifValuesByVariable: objectifMeta };
  }, [objectifMeta]);

  // Objectif item handlers
  const handleAddObjectifItem = () => {
    const firstVar = objectifVariables[0] || '';
    const rawValues = objectifValuesByVariable[firstVar];
    const values = Array.isArray(rawValues) ? rawValues : [];
    const newItem: ObjectifItem = {
      id: `obj_${Date.now()}`,
      variable: firstVar,
      type: values.length > 0 ? 'cat' : 'num',
      value: values.length > 0 ? values[0] : undefined,
      min: '',
      max: '',
    };
    setObjectifItems([...objectifItems, newItem]);
  };

  const handleRemoveObjectifItem = (itemId: string) => {
    setObjectifItems(objectifItems.filter(item => item.id !== itemId));
  };

  const handleObjectifItemChange = (itemId: string, field: keyof ObjectifItem, value: string) => {
    setObjectifItems(objectifItems.map(item => {
      if (item.id !== itemId) return item;

      if (field === 'variable') {
        const rawValues = objectifValuesByVariable[value];
        const values = Array.isArray(rawValues) ? rawValues : [];
        return {
          ...item,
          variable: value,
          type: values.length > 0 ? 'cat' : 'num',
          value: values.length > 0 ? values[0] : undefined,
          min: '',
          max: '',
        };
      }

      return { ...item, [field]: value };
    }));
  };

  // Build objectif JSON from items
  const buildObjectifJson = useCallback(() => {
    if (objectifItems.length === 0) return '';
    if (objectifItems.length === 1) {
      const item = objectifItems[0];
      if (item.type === 'cat' && item.value) {
        return item.value;
      } else if (item.type === 'num') {
        const obj: Record<string, number> = {};
        if (item.min) obj.min = parseFloat(item.min);
        if (item.max) obj.max = parseFloat(item.max);
        return Object.keys(obj).length > 0 ? JSON.stringify(obj) : '';
      }
    }
    // Multi-objectif
    const payload = {
      op: objectifOperator,
      items: objectifItems.map(item => {
        if (item.type === 'cat') {
          return { variable: item.variable, type: 'cat' as const, value: item.value };
        } else {
          const numItem: { variable: string; type: 'num'; min?: number; max?: number } = {
            variable: item.variable,
            type: 'num',
          };
          if (item.min) numItem.min = parseFloat(item.min);
          if (item.max) numItem.max = parseFloat(item.max);
          return numItem;
        }
      }),
    };
    return JSON.stringify(payload);
  }, [objectifItems, objectifOperator]);

  // Create modele mutation
  const createMutation = useMutation({
    mutationFn: (data: {
      is_editing: boolean;
      id_modele: string;
      nom_modele: string;
      variable_cible: string;
      objectif_value_for_store: string;
      blocks: any[];
    }) => apiClient.request(modelesApi.save(data)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['modeles'] });
      onSuccess?.();
      onClose();
      resetForm();
    },
    onError: (error: any) => {
      console.error('Error creating modele:', error);
      setErrors({ submit: 'Une erreur est survenue lors de la création du modèle' });
    },
  });

  const resetForm = () => {
    setFormData({
      nom_modele: '',
    });
    setObjectifOperator('AND');
    setObjectifItems([]);
    setBlocks([]);
    setExpandedBlocks(new Set());
    setErrors({});
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  // Helper: Check if blockId is a descendant of potentialAncestorId
  const isDescendant = (blockId: string, potentialAncestorId: string): boolean => {
    const block = blocks.find(b => b.id === blockId);
    if (!block || !block.parentBlockId) return false;
    if (block.parentBlockId === potentialAncestorId) return true;
    return isDescendant(block.parentBlockId, potentialAncestorId);
  };

  // Helper: Calculate depth of a block in the tree
  const getBlockDepth = (blockId: string): number => {
    const block = blocks.find(b => b.id === blockId);
    if (!block || !block.parentBlockId) return 0;
    return 1 + getBlockDepth(block.parentBlockId);
  };

  // Helper: Get blocks in tree traversal order (depth-first)
  const getOrderedBlocks = (): Block[] => {
    const ordered: Block[] = [];

    const addBlockAndChildren = (blockId: string | null) => {
      const children = blocks.filter(b => b.parentBlockId === blockId);
      children.forEach(child => {
        ordered.push(child);
        addBlockAndChildren(child.id);
      });
    };

    // Start with root blocks (parentBlockId === null)
    const roots = blocks.filter(b => b.parentBlockId === null);
    roots.forEach(root => {
      ordered.push(root);
      addBlockAndChildren(root.id);
    });

    return ordered;
  };

  // Helper: Get display number for a block (based on tree traversal)
  const getBlockDisplayNumber = (blockId: string): number => {
    const orderedBlocks = getOrderedBlocks();
    return orderedBlocks.findIndex(b => b.id === blockId) + 1;
  };

  const handleAddBlock = (parentId: string | null = null) => {
    const defaultCanal = canauxData?.canaux[0] || 'Appel';

    const newBlock: Block = {
      id: `block_${Date.now()}`,
      canal: defaultCanal,
      delai: 0,
      parentBlockId: parentId,
      conditions: [],
    };
    setBlocks([...blocks, newBlock]);
    setExpandedBlocks(new Set([...expandedBlocks, newBlock.id]));
  };

  const handleAddCondition = (blockId: string, type: ConditionType) => {
    setBlocks(blocks.map(block => {
      if (block.id === blockId) {
        const newCondition: BlockCondition = {
          id: `cond_${Date.now()}_${type}`,
          type,
          nextBlockId: null,
        };

        if (type === 'days_since_last') {
          newCondition.daysSinceLastAction = 1;
        } else if (type === 'flag_resultat' && canauxData) {
          const results = canauxData.resultats_by_canal[block.canal] || [];
          newCondition.flagResultat = results[0] || '';
        } else if (type === 'counter') {
          newCondition.counterValue = 1;
        } else if (type === 'campaign_field') {
          newCondition.campaignField = 'nb_jour_debut_campagne';
          newCondition.campaignFieldValue = 0;
          newCondition.operator = '>=';
        }

        return {
          ...block,
          conditions: [...block.conditions, newCondition],
        };
      }
      return block;
    }));
  };

  const handleRemoveBlock = (id: string) => {
    const updatedBlocks = blocks.filter(block => block.id !== id);
    const cleanedBlocks = updatedBlocks.map(block => ({
      ...block,
      conditions: block.conditions.map(cond => ({
        ...cond,
        nextBlockId: cond.nextBlockId === id ? null : cond.nextBlockId,
      })),
    }));

    setBlocks(cleanedBlocks);
    const newExpanded = new Set(expandedBlocks);
    newExpanded.delete(id);
    setExpandedBlocks(newExpanded);
  };

  const handleRemoveCondition = (blockId: string, conditionId: string) => {
    setBlocks(blocks.map(block => {
      if (block.id === blockId) {
        return {
          ...block,
          conditions: block.conditions.filter(c => c.id !== conditionId),
        };
      }
      return block;
    }));
  };

  const handleBlockChange = (id: string, field: keyof Block, value: any) => {
    setBlocks(blocks.map(block => {
      if (block.id === id) {
        return { ...block, [field]: value };
      }
      return block;
    }));
  };

  const handleConditionChange = (blockId: string, conditionId: string, field: string, value: any) => {
    setBlocks(blocks.map(block => {
      if (block.id === blockId) {
        return {
          ...block,
          conditions: block.conditions.map(cond =>
            cond.id === conditionId ? { ...cond, [field]: value } : cond
          ),
        };
      }
      return block;
    }));
  };

  const toggleBlockExpanded = (blockId: string) => {
    const newExpanded = new Set(expandedBlocks);
    if (newExpanded.has(blockId)) {
      newExpanded.delete(blockId);
    } else {
      newExpanded.add(blockId);
    }
    setExpandedBlocks(newExpanded);
  };

  const showDeleteBlockedToast = () => {
    setToast({
      isOpen: true,
      title: 'Suppression impossible',
      message: 'Ce bloc a des blocs enfants. Supprimez d abord les enfants.',
      type: 'warning',
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const newErrors: Record<string, string> = {};

    if (!formData.nom_modele.trim()) {
      newErrors.nom_modele = 'Le nom du modèle est requis';
    }
    if (blocks.length === 0) {
      newErrors.blocks = 'Au moins une action est requise';
    }

    // Validate parent relationships
    const rootBlocks = blocks.filter(b => b.parentBlockId === null);
    if (rootBlocks.length === 0) {
      newErrors.blocks = 'Au moins un bloc racine est requis';
    }

    blocks.forEach((block) => {
      const blockNumber = getBlockDisplayNumber(block.id);

      // Non-root blocks must have a parent
      if (block.parentBlockId === '' || (block.parentBlockId === null && rootBlocks.length > 1 && rootBlocks[0].id !== block.id)) {
        newErrors[`block_${block.id}_parent`] = `Le bloc ${blockNumber} doit avoir un bloc parent`;
      }

      // Check for circular references
      if (block.parentBlockId && isDescendant(block.parentBlockId, block.id)) {
        newErrors[`block_${block.id}_circular`] = `Le bloc ${blockNumber} crée une référence circulaire`;
      }
    });

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    // Derive variable_cible from first objectif item
    const derivedVariableCible = objectifItems.length > 0 ? objectifItems[0].variable : '';

    const payload = {
      is_editing: false,
      id_modele: '',
      nom_modele: formData.nom_modele,
      variable_cible: derivedVariableCible,
      objectif_value_for_store: buildObjectifJson(),
      blocks: blocks.map(block => ({
        id: block.id,
        canal: block.canal,
        action: canauxData?.actions_by_canal[block.canal] || block.canal,
        delai: 0,  // Always 0 since we removed the field
        parentBlockId: block.parentBlockId,  // Parent relationship
        objet: block.objet || '',
        contenu: block.contenu || '',
        compteur: (() => {
          const parentBlock = blocks.find(b => b.id === block.parentBlockId);
          const parentCanal = parentBlock?.canal || block.canal;
          return canauxData?.compteur_by_canal[parentCanal] || 'NB_appel';
        })(),
        conditions: block.conditions.map(cond => ({
          type: cond.type,
          operator: cond.operator || '=',
          daysSinceLastAction: cond.daysSinceLastAction,
          flagResultat: cond.flagResultat,
          counterValue: cond.counterValue,
          campaignField: cond.campaignField,
          campaignFieldValue: cond.campaignFieldValue,
          nextBlockId: cond.nextBlockId,
        })),
      })),
    };

    createMutation.mutate(payload);
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

  const isMetaLoading = canauxLoading || variablesLoading;

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={handleClose}
    >
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />
      <div
        className="relative bg-white rounded-2xl shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white flex items-center justify-between p-6 border-b border-gray-200 z-10">
          <h2 className="text-2xl font-bold text-gray-900">Nouveau Modèle</h2>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-gray-100 rounded-full transition-colors"
            aria-label="Close"
          >
            <X className="w-6 h-6 text-gray-600" />
          </button>
        </div>

        {isMetaLoading ? (
          <div className="p-12 text-center">
            <LoadingSpinner size="lg" />
            <p className="text-gray-500 mt-4">Chargement des métadonnées...</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-6">
            <div>
              <label htmlFor="nom_modele" className="block text-sm font-medium text-gray-700 mb-2">
                Nom du modèle <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                id="nom_modele"
                value={formData.nom_modele}
                onChange={(e) => {
                  setFormData({ ...formData, nom_modele: e.target.value });
                  setErrors({ ...errors, nom_modele: '' });
                }}
                className={`w-full px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 ${
                  errors.nom_modele ? 'border-red-500' : 'border-gray-300'
                }`}
                placeholder="Ex: Modèle Activation Carte"
              />
              {errors.nom_modele && <p className="mt-1 text-sm text-red-500">{errors.nom_modele}</p>}
            </div>

            {/* Objectifs Section */}
            <div className="border-t pt-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Objectifs
                  </label>
                  <p className="text-xs text-gray-500 mt-1">
                    Définissez un ou plusieurs critères d'objectif
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {objectifItems.length > 1 && (
                    <select
                      value={objectifOperator}
                      onChange={(e) => setObjectifOperator(e.target.value as 'AND' | 'OR')}
                      className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-900"
                    >
                      <option value="AND">ET (AND)</option>
                      <option value="OR">OU (OR)</option>
                    </select>
                  )}
                  <button
                    type="button"
                    onClick={handleAddObjectifItem}
                    className="flex items-center gap-1 px-3 py-1.5 bg-slate-900 text-white rounded-lg text-sm hover:bg-slate-800"
                  >
                    <Plus className="w-4 h-4" />
                    Ajouter
                  </button>
                </div>
              </div>

              {objectifItems.length === 0 ? (
                <div className="p-6 border-2 border-dashed border-gray-300 rounded-lg text-center">
                  <p className="text-gray-500 text-sm">Aucun objectif défini. Cliquez sur "Ajouter" pour commencer.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {objectifItems.map((item, index) => {
                    const rawItemValues = objectifValuesByVariable[item.variable];
                    const itemValues = Array.isArray(rawItemValues) ? rawItemValues : [];
                    const isItemCategorical = itemValues.length > 0;

                    return (
                      <div key={item.id} className="p-4 border rounded-lg bg-gray-50">
                        <div className="flex items-start gap-4">
                          <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-4">
                            {/* Variable selector */}
                            <div>
                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                Variable {index + 1}
                              </label>
                              <select
                                value={item.variable}
                                onChange={(e) => handleObjectifItemChange(item.id, 'variable', e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-900"
                              >
                                <option value="">Sélectionner...</option>
                                {objectifVariables.map((variable) => (
                                  <option key={variable} value={variable}>
                                    {variable}
                                  </option>
                                ))}
                              </select>
                            </div>

                            {/* Value input - categorical or numeric */}
                            {isItemCategorical ? (
                              <div className="md:col-span-2">
                                <label className="block text-xs font-medium text-gray-600 mb-1">
                                  Valeur
                                </label>
                                <select
                                  value={item.value || ''}
                                  onChange={(e) => handleObjectifItemChange(item.id, 'value', e.target.value)}
                                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-900"
                                >
                                  <option value="">Sélectionner...</option>
                                  {itemValues.map((val) => (
                                    <option key={val} value={val}>
                                      {val}
                                    </option>
                                  ))}
                                </select>
                              </div>
                            ) : (
                              <>
                                <div>
                                  <label className="block text-xs font-medium text-gray-600 mb-1">
                                    Min (optionnel)
                                  </label>
                                  <input
                                    type="text"
                                    value={item.min || ''}
                                    onChange={(e) => handleObjectifItemChange(item.id, 'min', e.target.value.replace(/[^0-9]/g, ''))}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-900"
                                    placeholder="Ex: 1000"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs font-medium text-gray-600 mb-1">
                                    Max (optionnel)
                                  </label>
                                  <input
                                    type="text"
                                    value={item.max || ''}
                                    onChange={(e) => handleObjectifItemChange(item.id, 'max', e.target.value.replace(/[^0-9]/g, ''))}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-slate-900"
                                    placeholder="Ex: 5000"
                                  />
                                </div>
                              </>
                            )}
                          </div>

                          {/* Remove button */}
                          <button
                            type="button"
                            onClick={() => handleRemoveObjectifItem(item.id)}
                            className="p-2 text-red-500 hover:bg-red-50 rounded-lg"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              {errors.objectif && <p className="mt-2 text-sm text-red-500">{errors.objectif}</p>}
            </div>

            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Workflow <span className="text-red-500">*</span>
                  </label>
                  <p className="text-xs text-gray-500 mt-1">
                    Construisez votre workflow avec des actions et des conditions
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleAddBlock(null)}
                  className="px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-2 text-sm"
                >
                  <Plus className="w-4 h-4" />
                  Ajouter une action
                </button>
              </div>

              {blocks.length === 0 ? (
                <div className="p-8 border-2 border-dashed border-gray-300 rounded-lg text-center">
                  <GitBranch className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500">Aucune action ajoutée. Commencez à construire votre workflow.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {getOrderedBlocks().map((block) => {
                    const depth = getBlockDepth(block.id);
                    const blockNumber = getBlockDisplayNumber(block.id);

                    return (
                      <div
                        key={block.id}
                        className="border border-gray-300 rounded-lg bg-white overflow-hidden"
                        style={{ marginLeft: `${depth * 2}rem` }}
                      >
                        <div className="p-4 bg-gray-50 border-b border-gray-200">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3 flex-1">
                              <span className="flex items-center justify-center w-8 h-8 bg-slate-900 text-white rounded-full text-sm font-bold">
                                {blockNumber}
                              </span>
                              <div className="flex-1 space-y-3">
                                {/* Parent Block selector - hide for root blocks */}
                                {block.parentBlockId !== null && (
                                  <div>
                                    <label className="block text-xs font-medium text-gray-600 mb-1">
                                      Bloc parent <span className="text-red-500">*</span>
                                    </label>
                                    <select
                                      value={block.parentBlockId || ''}
                                      onChange={(e) => handleBlockChange(block.id, 'parentBlockId', e.target.value)}
                                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 bg-white"
                                    >
                                      <option value="">Sélectionner un bloc parent...</option>
                                      {blocks
                                        .filter(b => b.id !== block.id)
                                        .filter(b => !isDescendant(b.id, block.id))
                                        .map((b) => {
                                          const bNumber = getBlockDisplayNumber(b.id);
                                          return (
                                            <option key={b.id} value={b.id}>
                                              Bloc {bNumber} - {b.canal}
                                            </option>
                                          );
                                        })}
                                    </select>
                                  </div>
                                )}

                                <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Canal</label>
                                <select
                                  value={block.canal}
                                  onChange={(e) => handleBlockChange(block.id, 'canal', e.target.value)}
                                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 bg-white"
                                >
                                  {canauxData?.canaux.map((canal) => (
                                    <option key={canal} value={canal}>
                                      {canal}
                                    </option>
                                  ))}
                                </select>
                              </div>

                              {/* Objet field - only for EMAIL */}
                              {block.canal === 'EMAIL' && (
                                <div>
                                  <label className="block text-xs font-medium text-gray-600 mb-1">Objet</label>
                                  <input
                                    type="text"
                                    value={block.objet || ''}
                                    onChange={(e) => handleBlockChange(block.id, 'objet', e.target.value)}
                                    placeholder="Sujet de l'email"
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                                  />
                                </div>
                              )}

                              {/* Contenu field - for all canals */}
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Contenu</label>
                                <textarea
                                  value={block.contenu || ''}
                                  onChange={(e) => handleBlockChange(block.id, 'contenu', e.target.value)}
                                  placeholder={
                                    block.canal === 'EMAIL'
                                      ? "Corps de l'email"
                                      : block.canal === 'SMS'
                                      ? "Message SMS"
                                      : "Message"
                                  }
                                  rows={3}
                                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none"
                                />
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            {/* Add Child Block button */}
                            <button
                              type="button"
                              onClick={() => handleAddBlock(block.id)}
                              className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors flex items-center gap-1"
                              title="Ajouter un bloc enfant"
                            >
                              <Plus className="w-3 h-3" />
                              Enfant
                            </button>

                            {/* Hide Conditions button for root blocks */}
                            {block.parentBlockId !== null && (
                              <button
                                type="button"
                                onClick={() => toggleBlockExpanded(block.id)}
                                className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors"
                              >
                                {expandedBlocks.has(block.id) ? 'Réduire' : 'Conditions'}
                              </button>
                            )}

                            {/* Delete button - check for children */}
                            <button
                              type="button"
                              onClick={() => {
                                const hasChildren = blocks.some(b => b.parentBlockId === block.id);
                                if (hasChildren) {
                                  showDeleteBlockedToast();
                                } else {
                                  handleRemoveBlock(block.id);
                                }
                              }}
                              className="p-2 text-red-600 hover:bg-red-50 rounded transition-colors"
                              title="Supprimer le bloc"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Conditions - Hide for root blocks */}
                      {expandedBlocks.has(block.id) && block.parentBlockId !== null && (
                        <div className="p-4 bg-blue-50">
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <GitBranch className="w-4 h-4 text-blue-600" />
                              <span className="text-sm font-medium text-blue-900">Conditions (liées au bloc mère)</span>
                            </div>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => handleAddCondition(block.id, 'days_since_last')}
                                className="px-2 py-1 text-xs bg-white border border-blue-300 rounded hover:bg-blue-50 transition-colors"
                              >
                                + NB jours depuis last action
                              </button>
                              <button
                                type="button"
                                onClick={() => handleAddCondition(block.id, 'flag_resultat')}
                                className="px-2 py-1 text-xs bg-white border border-blue-300 rounded hover:bg-blue-50 transition-colors"
                              >
                                + Flag résultats
                              </button>
                              <button
                                type="button"
                                onClick={() => handleAddCondition(block.id, 'counter')}
                                className="px-2 py-1 text-xs bg-white border border-blue-300 rounded hover:bg-blue-50 transition-colors"
                              >
                                + {(() => {
                                  const parentBlock = blocks.find(b => b.id === block.parentBlockId);
                                  const parentCanal = parentBlock?.canal || block.canal;
                                  return canauxData?.compteur_by_canal[parentCanal] || 'NB_appel';
                                })()}
                              </button>
                              <button
                                type="button"
                                onClick={() => handleAddCondition(block.id, 'campaign_field')}
                                className="px-2 py-1 text-xs bg-white border border-purple-300 rounded hover:bg-purple-50 transition-colors"
                              >
                                + NB jours depuis début campagne
                              </button>
                            </div>
                          </div>
                          <div className="space-y-2">
                            {block.conditions.length === 0 ? (
                              <div className="text-center py-6 text-gray-500 text-sm">
                                Aucune condition. Cliquez sur un bouton ci-dessus pour ajouter une condition.
                              </div>
                            ) : (
                              block.conditions.map((condition) => (
                                <div key={condition.id} className="bg-white p-3 rounded-lg border border-blue-200">
                                  <div className="flex items-start gap-3">
                                    <div className="flex-1">
                                      {condition.type === 'days_since_last' && (
                                        <div className="mb-2">
                                          <label className="block text-sm font-semibold text-gray-800 mb-2">
                                            NB jours depuis last action
                                          </label>
                                          <div className="grid grid-cols-2 gap-2">
                                            <div>
                                              <label className="block text-xs font-medium text-gray-600 mb-1">Opérateur</label>
                                              <select
                                                value={condition.operator || '='}
                                                onChange={(e) => handleConditionChange(block.id, condition.id, 'operator', e.target.value)}
                                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                              >
                                                <option value="=">=</option>
                                                <option value=">">{'>'}</option>
                                                <option value="<">{'<'}</option>
                                                <option value="<=">{'<='}</option>
                                                <option value=">=">{'>='}</option>
                                              </select>
                                            </div>
                                            <div>
                                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                                Valeur
                                              </label>
                                              <input
                                                type="number"
                                                value={condition.daysSinceLastAction || 1}
                                                onChange={(e) => handleConditionChange(block.id, condition.id, 'daysSinceLastAction', parseInt(e.target.value) || 1)}
                                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                                min="1"
                                              />
                                            </div>
                                          </div>
                                        </div>
                                      )}
                                      {condition.type === 'flag_resultat' && (
                                        <div className="mb-2">
                                          <label className="block text-sm font-semibold text-gray-800 mb-2">
                                            Flag résultats
                                          </label>
                                          <div className="grid grid-cols-2 gap-2">
                                            <div>
                                              <label className="block text-xs font-medium text-gray-600 mb-1">Opérateur</label>
                                              <select
                                                value="="
                                                disabled
                                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-gray-100"
                                              >
                                                <option value="=">=</option>
                                              </select>
                                            </div>
                                            <div>
                                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                                Valeur
                                              </label>
                                              <select
                                                value={condition.flagResultat || ''}
                                                onChange={(e) => handleConditionChange(block.id, condition.id, 'flagResultat', e.target.value)}
                                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                              >
                                                <option value="">Sélectionner...</option>
                                                <option value="Abouti">Abouti</option>
                                                <option value="Non Abouti">Non Abouti</option>
                                              </select>
                                            </div>
                                          </div>
                                        </div>
                                      )}
                                      {condition.type === 'counter' && (
                                        <div className="mb-2">
                                          <label className="block text-sm font-semibold text-gray-800 mb-2">
                                            {(() => {
                                              const parentBlock = blocks.find(b => b.id === block.parentBlockId);
                                              const parentCanal = parentBlock?.canal || block.canal;
                                              return canauxData?.compteur_by_canal[parentCanal] || 'NB_appel';
                                            })()}
                                          </label>
                                          <div className="grid grid-cols-2 gap-2">
                                            <div>
                                              <label className="block text-xs font-medium text-gray-600 mb-1">Opérateur</label>
                                              <select
                                                value={condition.operator || '='}
                                                onChange={(e) => handleConditionChange(block.id, condition.id, 'operator', e.target.value)}
                                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                              >
                                                <option value="=">=</option>
                                                <option value=">">{'>'}</option>
                                                <option value="<">{'<'}</option>
                                                <option value="<=">{'<='}</option>
                                                <option value=">=">{'>='}</option>
                                              </select>
                                            </div>
                                            <div>
                                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                                Valeur
                                              </label>
                                              <input
                                                type="number"
                                                value={condition.counterValue || 1}
                                                onChange={(e) => handleConditionChange(block.id, condition.id, 'counterValue', parseInt(e.target.value) || 1)}
                                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                                min="1"
                                              />
                                            </div>
                                          </div>
                                        </div>
                                      )}
                                      {condition.type === 'campaign_field' && (
                                        <div className="mb-2">
                                          <label className="block text-sm font-semibold text-gray-800 mb-2">
                                            {campaignConditionFields?.fields?.find(f => f.db_field === condition.campaignField)?.field || 'NB jours depuis début campagne'}
                                          </label>
                                          <div className="grid grid-cols-2 gap-2">
                                            <div>
                                              <label className="block text-xs font-medium text-gray-600 mb-1">Opérateur</label>
                                              <select
                                                value={condition.operator || '='}
                                                onChange={(e) => handleConditionChange(block.id, condition.id, 'operator', e.target.value)}
                                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                              >
                                                <option value="=">=</option>
                                                <option value=">">{'>'}</option>
                                                <option value="<">{'<'}</option>
                                                <option value="<=">{'<='}</option>
                                                <option value=">=">{'>='}</option>
                                              </select>
                                            </div>
                                            <div>
                                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                                Valeur (jours)
                                              </label>
                                              <input
                                                type="number"
                                                value={condition.campaignFieldValue ?? 0}
                                                onChange={(e) => handleConditionChange(block.id, condition.id, 'campaignFieldValue', parseInt(e.target.value) || 0)}
                                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                                min="0"
                                              />
                                            </div>
                                          </div>
                                        </div>
                                      )}
                                      <div>
                                        <label className="block text-xs font-medium text-gray-700 mb-1">Alors aller à</label>
                                        <select
                                          value={condition.nextBlockId || ''}
                                          onChange={(e) => handleConditionChange(block.id, condition.id, 'nextBlockId', e.target.value || null)}
                                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                        >
                                          <option value="">Fin du workflow</option>
                                          {blocks
                                            .filter(b => b.id !== block.id)
                                            .map((b) => {
                                              const bNumber = getBlockDisplayNumber(b.id);
                                              return (
                                                <option key={b.id} value={b.id}>
                                                  Bloc {bNumber} - {b.canal}
                                                </option>
                                              );
                                            })}
                                        </select>
                                      </div>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => handleRemoveCondition(block.id, condition.id)}
                                      className="p-1 text-red-600 hover:bg-red-50 rounded transition-colors mt-1"
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </button>
                                  </div>
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                    );
                  })}
                </div>
              )}
              {errors.blocks && <p className="mt-2 text-sm text-red-500">{errors.blocks}</p>}
            </div>

            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-800">
                <strong>Types de conditions:</strong>
                <br />• <strong>NB jours depuis last action:</strong> Condition temporelle (ex: "Après 3 jours")
                <br />• <strong>Flag résultats:</strong> Basée sur le résultat de l'action parent (ex: "Joignable avec succès")
                <br />• <strong>{canauxData?.compteur_by_canal[blocks[0]?.canal] || 'NB_appel'}:</strong> Basée sur le compteur du canal (ex: "2 appels")
              </p>
            </div>

            {errors.submit && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-600">{errors.submit}</p>
              </div>
            )}

            <div className="flex items-center justify-end gap-4 pt-4 border-t border-gray-200">
              <button
                type="button"
                onClick={handleClose}
                className="px-6 py-3 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors font-medium"
              >
                Annuler
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-6 py-3 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {createMutation.isPending && <LoadingSpinner size="sm" />}
                {createMutation.isPending ? 'Création...' : 'Créer le modèle'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
