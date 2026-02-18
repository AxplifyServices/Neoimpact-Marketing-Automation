import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2, GitBranch, X } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { metaApi } from '@/lib/api/definitions/meta.api';
import { getApiClient } from '@/lib/api/api-client';
import LoadingSpinner from '../../components/LoadingSpinner';
import Toast from '../../components/Toast';
import WorkflowPreview from '../../components/custom/WorkflowPreview';

interface Block {
  id: string;
  canal: string;
  delai: number;
  parentBlockId: string | null;
  objet?: string;
  contenu?: string;
  conditions: BlockCondition[];
}

type ConditionType = 'days_since_last' | 'flag_resultat' | 'counter' | 'client_filter' | 'campaign_field' | 'client_field';

interface BlockCondition {
  id: string;
  type: ConditionType;
  operator?: string;
  daysSinceLastAction?: number;
  flagResultat?: string;
  counterValue?: number;
  // Client filter fields (same as CibleFilter from CreateCiblePage)
  column?: string;
  min?: string;
  max?: string;
  values?: string[];
  // Campaign field (e.g. NB jours depuis début campagne)
  campaignField?: string;
  campaignFieldValue?: number;
  // Client field (e.g. client.carte_retiree)
  clientField?: string;
  clientFieldValue?: string;
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

interface EditPayload {
  id_modele: string;
  nom_modele: string;
  variable_cible: string;
  objectif?: string;
  objectif_value_for_store?: string | Record<string, unknown> | null;
  liste_action?: string;
  blocks?: any[] | string;
}

interface DuplicateState {
  duplicateId?: string;
}

type ConditionMetaResponse = Record<string, string[] | 'Numérique'>;
type ObjectifMetaResponse = Record<string, string[] | 'Numérique'>;

interface ObjectifItem {
  id: string;
  variable: string;
  type: 'cat' | 'num';
  value?: string;
  min?: string;
  max?: string;
}

export default function CreateModelePage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const isEditing = Boolean(id);
  const duplicateId = (location.state as DuplicateState | null)?.duplicateId;
  const isDuplicating = Boolean(duplicateId);
  const sourceId = isEditing ? id : duplicateId;
  const hasLoadedEdit = useRef(false);
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
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [isBlockModalOpen, setIsBlockModalOpen] = useState(false);
  const scrollContainerRef = useRef<HTMLElement | null>(null);
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' | 'warning' }>({
    isOpen: false,
    title: '',
  });

  // Fetch canaux metadata from API
  const { data: canauxData, isLoading: canauxLoading } = useQuery<CanauxMetadata>({
    queryKey: ['meta-canaux'],
    queryFn: () => apiClient.request<CanauxMetadata>(metaApi.getCanaux()),
  });

  // Fetch variables metadata from API (kept for backward compatibility)
  const { isLoading: variablesLoading } = useQuery<VariablesMetadata>({
    queryKey: ['meta-variables'],
    queryFn: () => apiClient.request<VariablesMetadata>(metaApi.getVariables()),
  });

  // Fetch condition metadata (fields and their possible values)
  const { data: conditionMeta, isLoading: conditionMetaLoading } = useQuery<ConditionMetaResponse>({
    queryKey: ['condition-meta'],
    queryFn: () => apiClient.request<ConditionMetaResponse>(metaApi.getConditionMeta()),
  });

  // Fetch objectif metadata (variables and their allowed values)
  const { data: objectifMeta, isLoading: objectifMetaLoading } = useQuery<ObjectifMetaResponse>({
    queryKey: ['objectif-meta'],
    queryFn: () => apiClient.request<ObjectifMetaResponse>(metaApi.getObjectifMeta()),
  });

  // Fetch campaign condition fields (e.g. NB jours depuis début campagne)
  const { data: campaignConditionFields } = useQuery<{ fields: CampaignConditionField[] }>({
    queryKey: ['campaign-condition-fields'],
    queryFn: () => apiClient.request<{ fields: CampaignConditionField[] }>(metaApi.getCampaignConditionFields()),
  });

  const { data: editPayload, isLoading: editLoading } = useQuery<EditPayload>({
    queryKey: ['modele-edit', sourceId],
    queryFn: () => apiClient.request<EditPayload>(modelesApi.getEditPayload(sourceId!)),
    enabled: !!sourceId,
    refetchOnWindowFocus: false,
  });

  // Derive field lists from meta data
  const { numFields, catFields, allFields, valuesByField } = useMemo(() => {
    if (!conditionMeta) {
      return {
        numFields: [] as string[],
        catFields: [] as string[],
        allFields: [] as string[],
        valuesByField: {} as Record<string, string[]>
      };
    }

    const numFields: string[] = [];
    const catFields: string[] = [];
    const valuesByField: Record<string, string[]> = {};

    Object.entries(conditionMeta).forEach(([field, value]) => {
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
  }, [conditionMeta]);

  // Derive objectif variables and their values from objectif meta
  const { objectifVariables, objectifValuesByVariable } = useMemo(() => {
    if (!objectifMeta) {
      return { objectifVariables: [] as string[], objectifValuesByVariable: {} as Record<string, string[]> };
    }
    return {
      objectifVariables: Object.keys(objectifMeta),
      objectifValuesByVariable: objectifMeta,
    };
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
  }, [objectifItems, objectifOperator, objectifValuesByVariable]);

  const getFieldKind = (field: string): 'numeric' | 'categorical' => numFields.includes(field) ? 'numeric' : 'categorical';
  const formatFieldLabel = (field: string) => {
    // Convert snake_case or camelCase to readable format
    return field
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const normalizeObjectifValue = (value: EditPayload['objectif_value_for_store'] | EditPayload['objectif']): string => {
    if (typeof value === 'string') {
      return value;
    }
    if (value && typeof value === 'object') {
      try {
        return JSON.stringify(value);
      } catch {
        return '';
      }
    }
    return '';
  };

  const normalizeCanal = (canal: string): string => canal.trim().toLowerCase();

  const isSpamSensitiveCanal = (canal: string): boolean => {
    const normalized = normalizeCanal(canal);
    return normalized === 'sms' || normalized === 'mail' || normalized === 'email';
  };

  const renderAntiSpamWarning = (canal: string) => {
    if (!isSpamSensitiveCanal(canal)) {
      return null;
    }

    const label = normalizeCanal(canal) === 'sms' ? 'SMS' : 'Email';
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        <span className="font-semibold">Attention anti-spam ({label})</span>
        <span className="ml-2">
          Verifier consentement, identite expediteur et desabonnement. Le recepteur ne sera pas spamme par des messages similaires.
        </span>
      </div>
    );
  };

  const normalizeParentId = (value: unknown): string | null => {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    if (typeof value === 'string') {
      if (value.startsWith('block_')) return value;
      if (/^\d+$/.test(value)) return `block_${value}`;
      return value;
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      return `block_${value}`;
    }
    return null;
  };

  const convertOldFormatToNew = (parsedBlocks: any[]): Block[] => {
    if (!Array.isArray(parsedBlocks) || parsedBlocks.length === 0) return [];

    return parsedBlocks.map((oldBlock: any, blockIndex: number) => ({
      id: `block_${oldBlock.ID ?? blockIndex}`,
      canal: oldBlock.Canal || '',
      delai: Number(oldBlock.Delai) || 0,
      parentBlockId: normalizeParentId(oldBlock['Bloc_mère'] ?? oldBlock['Bloc_mere']),
      objet: oldBlock.Objet || '',
      contenu: oldBlock.Contenu || '',
      conditions: (oldBlock.Conditions || []).map((oldCond: any, idx: number) => {
        const condition: BlockCondition = {
          id: `cond_${oldBlock.ID ?? blockIndex}_${idx}`,
          type: 'flag_resultat',
          nextBlockId: normalizeParentId(oldCond.next_block_id ?? oldCond.nextBlockId),
        };

        if (oldCond.field === 'Flag résultats' || oldCond.field === 'flag_resultat') {
          condition.type = 'flag_resultat';
          condition.flagResultat = oldCond.value;
          condition.operator = oldCond.op || '=';
        } else if (oldCond.field === 'days_since_last_action' || oldCond.field === 'NB jours depuis last action') {
          condition.type = 'days_since_last';
          condition.daysSinceLastAction = oldCond.value;
          condition.operator = oldCond.op || '>';
        } else if (oldCond.field?.includes('NB_') || oldCond.field === 'counter') {
          condition.type = 'counter';
          condition.counterValue = oldCond.value;
          condition.operator = oldCond.op || '>';
        } else if (oldCond.field?.startsWith('client.')) {
          condition.type = 'client_field';
          condition.clientField = oldCond.field.replace('client.', '');
          condition.clientFieldValue = oldCond.value;
          condition.operator = oldCond.op || '=';
        } else if (oldCond.field === 'nb_jour_debut_campagne') {
          condition.type = 'campaign_field';
          condition.campaignField = oldCond.field;
          condition.campaignFieldValue = oldCond.value;
          condition.operator = oldCond.op || '>=';
        }

        return condition;
      }),
    }));
  };

  const normalizeConditions = (conditions: any[], blockId: string): BlockCondition[] => {
    if (!Array.isArray(conditions)) return [];
    return conditions.map((cond, idx) => {
      const base: BlockCondition = {
        id: typeof cond?.id === 'string' ? cond.id : `cond_${blockId}_${idx}`,
        type: cond?.type || 'flag_resultat',
        nextBlockId: normalizeParentId(cond?.nextBlockId ?? cond?.next_block_id),
      };

      if (cond?.type === 'days_since_last') {
        base.operator = cond.operator || '=';
        base.daysSinceLastAction = cond.daysSinceLastAction ?? cond.value;
      } else if (cond?.type === 'flag_resultat') {
        base.operator = cond.operator || '=';
        base.flagResultat = cond.flagResultat ?? cond.value;
      } else if (cond?.type === 'counter') {
        base.operator = cond.operator || '=';
        base.counterValue = cond.counterValue ?? cond.value;
      } else if (cond?.type === 'campaign_field') {
        base.operator = cond.operator || '>=';
        base.campaignField = cond.campaignField ?? cond.field;
        base.campaignFieldValue = cond.campaignFieldValue ?? cond.value;
      } else if (cond?.type === 'client_field') {
        base.operator = cond.operator || '=';
        base.clientField = cond.clientField ?? cond.field?.replace('client.', '');
        base.clientFieldValue = cond.clientFieldValue ?? cond.value;
      } else if (cond?.field) {
        if (cond.field === 'Flag résultats' || cond.field === 'flag_resultat') {
          base.type = 'flag_resultat';
          base.flagResultat = cond.value;
          base.operator = cond.op || '=';
        } else if (cond.field === 'days_since_last_action' || cond.field === 'NB jours depuis last action') {
          base.type = 'days_since_last';
          base.daysSinceLastAction = cond.value;
          base.operator = cond.op || '>';
        } else if (cond.field?.includes('NB_') || cond.field === 'counter') {
          base.type = 'counter';
          base.counterValue = cond.value;
          base.operator = cond.op || '>';
        } else if (cond.field?.startsWith('client.')) {
          base.type = 'client_field';
          base.clientField = cond.field.replace('client.', '');
          base.clientFieldValue = cond.value;
          base.operator = cond.op || '=';
        } else if (cond.field === 'nb_jour_debut_campagne') {
          base.type = 'campaign_field';
          base.campaignField = cond.field;
          base.campaignFieldValue = cond.value;
          base.operator = cond.op || '>=';
        }
      }

      return base;
    });
  };

  const normalizeBlocks = (rawBlocks: any[]): Block[] => {
    if (!Array.isArray(rawBlocks) || rawBlocks.length === 0) return [];

    const isOldFormat = rawBlocks.length > 0
      && rawBlocks[0]
      && typeof rawBlocks[0] === 'object'
      && 'ID' in rawBlocks[0];
    const baseBlocks = isOldFormat ? convertOldFormatToNew(rawBlocks) : rawBlocks;

    return baseBlocks.map((block: any, index: number) => {
      const idValue = block.id ?? block.ID;
      const id = typeof idValue === 'string'
        ? (idValue.trim() === ''
          ? `block_${Date.now()}_${index}`
          : (/^\d+$/.test(idValue.trim()) ? `block_${idValue.trim()}` : idValue))
        : typeof idValue === 'number'
          ? `block_${idValue}`
          : `block_${Date.now()}_${index}`;

      const parentBlockId = normalizeParentId(block.parentBlockId ?? block['Bloc_mère'] ?? block['Bloc_mere']);
      const conditions = normalizeConditions(block.conditions ?? block.Conditions ?? [], id);

      return {
        id,
        canal: block.canal ?? block.Canal ?? '',
        delai: Number(block.delai ?? block.Delai) || 0,
        parentBlockId,
        objet: block.objet ?? block.Objet ?? '',
        contenu: block.contenu ?? block.Contenu ?? '',
        conditions,
      };
    });
  };

  const resolveBlocksFromPayload = (payload: EditPayload): Block[] => {
    if (Array.isArray(payload.blocks) && payload.blocks.length > 0) {
      return normalizeBlocks(payload.blocks);
    }
    if (typeof payload.blocks === 'string') {
      try {
        const parsed = JSON.parse(payload.blocks);
        return normalizeBlocks(parsed);
      } catch {
        return [];
      }
    }
    if (payload.liste_action) {
      try {
        const parsed = JSON.parse(payload.liste_action);
        return normalizeBlocks(parsed);
      } catch {
        return [];
      }
    }
    return [];
  };

  useEffect(() => {
    hasLoadedEdit.current = false;
  }, [sourceId]);

  // Parse objectif value from editPayload into objectifItems
  const parseObjectifToItems = useCallback((variable: string, value: string): ObjectifItem[] => {
    if (!value || value.trim() === '') return [];

    try {
      const parsed = JSON.parse(value);
      // Multi-objectif format: {"op": "AND", "items": [...]}
      if (parsed && parsed.op && Array.isArray(parsed.items)) {
        setObjectifOperator(parsed.op);
        return parsed.items.map((item: any, idx: number) => ({
          id: `obj_edit_${idx}`,
          variable: item.variable || variable,
          type: item.type || 'cat',
          value: item.value,
          min: item.min !== undefined ? String(item.min) : '',
          max: item.max !== undefined ? String(item.max) : '',
        }));
      }
      // Numeric format: {"min": x, "max": y}
      if (parsed && (parsed.min !== undefined || parsed.max !== undefined)) {
        return [{
          id: `obj_edit_0`,
          variable,
          type: 'num',
          min: parsed.min !== undefined ? String(parsed.min) : '',
          max: parsed.max !== undefined ? String(parsed.max) : '',
        }];
      }
    } catch {
      // Not JSON - categorical value
    }

    // Simple categorical value
    return [{
      id: `obj_edit_0`,
      variable,
      type: 'cat',
      value,
    }];
  }, []);

  useEffect(() => {
    if ((!isEditing && !isDuplicating) || !editPayload || hasLoadedEdit.current) {
      return;
    }

    hasLoadedEdit.current = true;
    const objectifValue = normalizeObjectifValue(editPayload.objectif_value_for_store ?? editPayload.objectif ?? '');
    const loadedBlocks = resolveBlocksFromPayload(editPayload);

    setFormData({
      nom_modele: editPayload.nom_modele || '',
    });

    // Parse objectif into items
    const items = parseObjectifToItems(editPayload.variable_cible || '', objectifValue);
    setObjectifItems(items);

    setBlocks(loadedBlocks);
    setExpandedBlocks(new Set());
    setErrors({});
  }, [editPayload, isEditing, isDuplicating, parseObjectifToItems]);

  useEffect(() => {
    if (!canauxLoading && !isEditing && !isDuplicating && blocks.length === 0) {
      handleAddBlock(null);
    }
  }, [canauxLoading, blocks.length, isEditing, isDuplicating]);

  useEffect(() => {
    if (!scrollContainerRef.current) {
      scrollContainerRef.current = document.querySelector('main');
    }
  }, []);

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
      setToast({
        isOpen: true,
        title: 'Succes',
        message: isEditing
          ? 'Le modele a ete mis a jour avec succes'
          : 'Le modele a ete cree avec succes',
        type: 'success',
      });
      setTimeout(() => {
        navigate('/modeles');
      }, 1500);
    },
    onError: (error: any) => {
      console.error(isEditing ? 'Error updating modele:' : 'Error creating modele:', error);
      setToast({
        isOpen: true,
        title: 'Erreur',
        message: isEditing
          ? 'Une erreur est survenue lors de la mise a jour du modele'
          : 'Une erreur est survenue lors de la creation du modele',
        type: 'error',
      });
    },
  });

  // Helper functions
  const isDescendant = (blockId: string, potentialAncestorId: string): boolean => {
    const block = blocks.find(b => b.id === blockId);
    if (!block || !block.parentBlockId) return false;
    if (block.parentBlockId === potentialAncestorId) return true;
    return isDescendant(block.parentBlockId, potentialAncestorId);
  };

  const getBlockDepth = (blockId: string): number => {
    const block = blocks.find(b => b.id === blockId);
    if (!block || !block.parentBlockId) return 0;
    return 1 + getBlockDepth(block.parentBlockId);
  };

  const getOrderedBlocks = (): Block[] => {
    const ordered: Block[] = [];

    const addBlockAndChildren = (blockId: string | null) => {
      const children = blocks.filter(b => b.parentBlockId === blockId);
      children.forEach(child => {
        ordered.push(child);
        addBlockAndChildren(child.id);
      });
    };

    const roots = blocks.filter(b => b.parentBlockId === null);
    roots.forEach(root => {
      ordered.push(root);
      addBlockAndChildren(root.id);
    });

    return ordered;
  };

  const getBlockDisplayNumber = (blockId: string): number => {
    const orderedBlocks = getOrderedBlocks();
    return orderedBlocks.findIndex(b => b.id === blockId) + 1;
  };

  /**
   * Get hierarchical block number (e.g., 1, 1.1, 1.2, 2, 2.1)
   */
  const getHierarchicalNumber = (blockId: string): string => {
    const block = blocks.find(b => b.id === blockId);
    if (!block) return '';

    if (!block.parentBlockId) {
      // Root block - count position among roots
      const roots = blocks.filter(b => !b.parentBlockId);
      return String(roots.findIndex(b => b.id === blockId) + 1);
    }

    // Child block - parent number + position among siblings
    const parentNumber = getHierarchicalNumber(block.parentBlockId);
    const siblings = blocks.filter(b => b.parentBlockId === block.parentBlockId);
    const position = siblings.findIndex(b => b.id === blockId) + 1;
    return `${parentNumber}.${position}`;
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
    setBlocks((prev) => [...prev, newBlock]);
    setExpandedBlocks((prev) => {
      if (parentId !== null) {
        return new Set([newBlock.id]);
      }
      const next = new Set(prev);
      next.add(newBlock.id);
      return next;
    });
    return newBlock.id;
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
          newCondition.operator = '=';
        } else if (type === 'flag_resultat' && canauxData) {
          const results = canauxData.resultats_by_canal[block.canal] || [];
          newCondition.flagResultat = results[0] || '';
          newCondition.operator = '=';
        } else if (type === 'counter') {
          newCondition.counterValue = 1;
          newCondition.operator = '=';
        } else if (type === 'client_filter') {
          // Initialize with empty filter (user will select field)
          newCondition.column = '';
          newCondition.min = '';
          newCondition.max = '';
          newCondition.values = [];
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

  const handleRemoveBlock = (blockId: string) => {
    setBlocks(blocks.filter(b => b.id !== blockId));
    setExpandedBlocks(new Set([...expandedBlocks].filter(id => id !== blockId)));
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

  const handleBlockChange = (blockId: string, field: keyof Block, value: any) => {
    setBlocks(blocks.map(block => {
      if (block.id === blockId) {
        return { ...block, [field]: value };
      }
      return block;
    }));
  };

  const handleConditionChange = (blockId: string, conditionId: string, field: keyof BlockCondition, value: any) => {
    setBlocks(blocks.map(block => {
      if (block.id === blockId) {
        return {
          ...block,
          conditions: block.conditions.map(cond => {
            if (cond.id === conditionId) {
              return { ...cond, [field]: value };
            }
            return cond;
          }),
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

  const openBlockModal = (blockId: string) => {
    setActiveBlockId(blockId);
    setIsBlockModalOpen(true);
    setExpandedBlocks((prev) => {
      const next = new Set(prev);
      next.add(blockId);
      return next;
    });
  };

  const handleWorkflowSelect = (blockId: string) => {
    openBlockModal(blockId);
  };

  const handleWorkflowAddChild = (parentId: string) => {
    const newBlockId = handleAddBlock(parentId);
    openBlockModal(newBlockId);
  };

  const closeBlockModal = useCallback(() => {
    setIsBlockModalOpen(false);
  }, []);

  useEffect(() => {
    const scrollContainer = scrollContainerRef.current || document.querySelector('main');
    if (!scrollContainer) {
      return;
    }

    if (isBlockModalOpen) {
      return;
    }

    requestAnimationFrame(() => {
      scrollContainer.scrollTop = scrollContainer.scrollHeight;
    });
    setTimeout(() => {
      scrollContainer.scrollTop = scrollContainer.scrollHeight;
    }, 80);
  }, [isBlockModalOpen]);

  useEffect(() => {
    if (!isBlockModalOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeBlockModal();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [closeBlockModal, isBlockModalOpen]);

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

      if (block.parentBlockId === '' || (block.parentBlockId === null && rootBlocks.length > 1 && rootBlocks[0].id !== block.id)) {
        newErrors[`block_${block.id}_parent`] = `Le bloc ${blockNumber} doit avoir un bloc parent`;
      }

      if (block.parentBlockId && isDescendant(block.parentBlockId, block.id)) {
        newErrors[`block_${block.id}_circular`] = `Le bloc ${blockNumber} crée une référence circulaire`;
      }
    });

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    // Create ID mapping (sequential IDs starting from 1)
    const blockIdMapping = new Map<string, number>();
    const orderedBlocks = getOrderedBlocks();
    orderedBlocks.forEach((block, index) => {
      blockIdMapping.set(block.id, index + 1);
    });

    // Derive variable_cible from first objectif item
    const derivedVariableCible = objectifItems.length > 0 ? objectifItems[0].variable : '';

    const payload = {
      is_editing: isEditing,
      id_modele: isEditing ? (id || '') : '',
      nom_modele: formData.nom_modele,
      variable_cible: derivedVariableCible,
      objectif_value_for_store: buildObjectifJson(),
      blocks: orderedBlocks.map(block => ({
        ID: blockIdMapping.get(block.id),
        Bloc_mère: block.parentBlockId ? String(blockIdMapping.get(block.parentBlockId)) : '',
        Canal: block.canal,
        Action: canauxData?.actions_by_canal[block.canal] || block.canal,
        Objet: block.canal === 'Mail' || block.canal === 'EMAIL' ? (block.objet || '') : '',
        Contenu: block.contenu || '',
        Conditions: block.conditions.map(cond => {
          const condition: any = {};

          if (cond.type === 'flag_resultat' && cond.flagResultat) {
            condition.field = 'Flag résultats';
            condition.op = cond.operator || '=';
            condition.value = cond.flagResultat;
          } else if (cond.type === 'days_since_last' && cond.daysSinceLastAction !== undefined) {
            condition.field = 'NB jours depuis last action';
            condition.op = cond.operator || '=';
            condition.value = cond.daysSinceLastAction;
          } else if (cond.type === 'counter' && cond.counterValue !== undefined) {
            const parentBlock = blocks.find(b => b.id === block.parentBlockId);
            const parentCanal = parentBlock?.canal || block.canal;
            const compteur = canauxData?.compteur_by_canal[parentCanal] || 'NB_appel';
            condition.field = compteur;
            condition.op = cond.operator || '=';
            condition.value = cond.counterValue;
          } else if (cond.type === 'campaign_field' && cond.campaignField) {
            condition.field = cond.campaignField;
            condition.op = cond.operator || '=';
            condition.value = cond.campaignFieldValue ?? 0;
          } else if (cond.type === 'client_field' && cond.clientField) {
            condition.field = `client.${cond.clientField}`;
            condition.op = cond.operator || '=';
            condition.value = cond.clientFieldValue;
          }

          return condition;
        }).filter(c => Object.keys(c).length > 0),
      })),
    };

    createMutation.mutate(payload);
  };

  const isMetaLoading = canauxLoading || variablesLoading || conditionMetaLoading || objectifMetaLoading || ((isEditing || isDuplicating) && editLoading);

  // Use useMemo to ensure selectedBlock always reflects the current blocks state
  const selectedBlock = useMemo(() => {
    return activeBlockId ? blocks.find((block) => block.id === activeBlockId) : null;
  }, [activeBlockId, blocks]);

  const selectedBlockNumber = selectedBlock ? getHierarchicalNumber(selectedBlock.id) : '';
  const selectedHasChildren = selectedBlock
    ? blocks.some((block) => block.parentBlockId === selectedBlock.id)
    : false;

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
      <Toast
        isOpen={toast.isOpen}
        onClose={() => setToast({ ...toast, isOpen: false })}
        title={toast.title}
        message={toast.message}
        type={toast.type}
      />

      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <button
          onClick={() => navigate('/modeles')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>Retour aux modèles</span>
        </button>

        <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">
          {isEditing ? 'Modifier le modele' : 'Nouveau modele'}
        </h1>
        <p className="text-gray-600 mt-2">
          {isEditing
            ? 'Modifiez le modele de campagne avec des actions et des conditions'
            : 'Creez un nouveau modele de campagne avec des actions et des conditions'}
        </p>
      </div>

      {isMetaLoading ? (
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="max-w-7xl mx-auto">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-6">
            {/* Basic Information */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Nom du modèle <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formData.nom_modele}
                  onChange={(e) => setFormData({ ...formData, nom_modele: e.target.value })}
                  className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
                    errors.nom_modele ? 'border-red-500' : 'border-gray-300'
                  }`}
                  placeholder="Ex: Campagne de relance"
                />
                {errors.nom_modele && <p className="mt-1 text-sm text-red-500">{errors.nom_modele}</p>}
              </div>

              {/* Objectifs Section */}
              <div className="col-span-2 border-t pt-4 mt-2">
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
                        className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="AND">ET (AND)</option>
                        <option value="OR">OU (OR)</option>
                      </select>
                    )}
                    <button
                      type="button"
                      onClick={handleAddObjectifItem}
                      className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
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
                                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
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
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
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
                                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
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
                                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
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
                {errors.objectif_value_for_store && <p className="mt-2 text-sm text-red-500">{errors.objectif_value_for_store}</p>}
              </div>
            </div>

            {/* Workflow Section */}
            <div className="border-t pt-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Workflow <span className="text-red-500">*</span>
                  </label>
                  <p className="text-xs text-gray-500 mt-1">
                    Construisez votre workflow avec des actions et des conditions
                  </p>
                </div>
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
                    const hierarchicalNumber = getHierarchicalNumber(block.id);
                    const isChildBlock = block.parentBlockId !== null;
                    const isExpanded = expandedBlocks.has(block.id);
                    const conditionCount = block.conditions.length;
                    const conditionLabel = conditionCount === 1 ? 'condition' : 'conditions';

                    return (
                      <div
                        key={block.id}
                        className="border border-gray-300 rounded-lg bg-white overflow-hidden"
                        style={{ marginLeft: `${depth * 2}rem` }}
                      >
                        <div className="p-4 bg-gray-50 border-b border-gray-200">
                          <div className={`flex items-center justify-between ${isExpanded ? 'mb-4' : ''}`}>
                            <div className="flex items-center gap-3 flex-1">
                              <span className="flex items-center justify-center w-8 h-8 bg-slate-900 text-white rounded-full text-sm font-bold">
                                {hierarchicalNumber}
                              </span>
                              <div className="flex-1">
                                <div className="text-sm font-semibold text-gray-900">Canal: {block.canal}</div>
                                <div className="text-xs text-gray-600">
                                  <span>Delai: {block.delai}</span>
                                  {isChildBlock && (
                                    <span className="ml-2">- {conditionCount} {conditionLabel}</span>
                                  )}
                                </div>
                                <div className={`mt-3 space-y-3 ${isExpanded ? '' : 'hidden'}`}>
                                {/* Parent Block selector - hide for root blocks */}
                                {block.parentBlockId !== null && (
                                  <div>
                                    <label className="block text-xs font-medium text-gray-600 mb-1">
                                      Bloc parent <span className="text-red-500">*</span>
                                    </label>
                                    <select
                                      value={block.parentBlockId || ''}
                                      onChange={(e) => handleBlockChange(block.id, 'parentBlockId', e.target.value)}
                                      disabled={true}
                                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-gray-100 cursor-not-allowed"
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

                                {/* Objet field - only for Mail */}
                                {(block.canal === 'Mail' || block.canal === 'EMAIL') && (
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

                                {renderAntiSpamWarning(block.canal)}

                                {/* Contenu field - for all canals */}
                                <div>
                                  <label className="block text-xs font-medium text-gray-600 mb-1">Contenu</label>
                                  <textarea
                                    value={block.contenu || ''}
                                    onChange={(e) => handleBlockChange(block.id, 'contenu', e.target.value)}
                                    placeholder={
                                      block.canal === 'Mail' || block.canal === 'EMAIL'
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
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
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

                            {/* Toggle details */}
                            <button
                              type="button"
                              onClick={() => toggleBlockExpanded(block.id)}
                              className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors"
                            >
                              {isExpanded ? 'Reduire' : 'Details'}
                            </button>

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

                        {/* Conditions - child blocks only */}
                        {isExpanded && isChildBlock && (
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
                                  onClick={() => handleAddCondition(block.id, 'client_filter')}
                                  className="px-2 py-1 text-xs bg-white border border-blue-300 rounded hover:bg-blue-50 transition-colors"
                                >
                                  + Filtre client
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
                                                  {(() => {
                                                    // Get parent block's canal to determine available resultats
                                                    const parentBlock = blocks.find(b => b.id === block.parentBlockId);
                                                    const parentCanal = parentBlock?.canal;
                                                    const availableResultats = parentCanal
                                                      ? (canauxData?.resultats_by_canal[parentCanal] || [])
                                                      : [];

                                                    return availableResultats.map((resultat) => (
                                                      <option key={resultat} value={resultat}>
                                                        {resultat}
                                                      </option>
                                                    ));
                                                  })()}
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
                                        {condition.type === 'client_filter' && (
                                          <div className="mb-2">
                                            <label className="block text-sm font-semibold text-gray-800 mb-2">
                                              Filtre client
                                            </label>
                                            <div className="space-y-3">
                                              <div>
                                                <label className="block text-xs font-medium text-gray-600 mb-1">Colonne</label>
                                                <select
                                                  value={condition.column || ''}
                                                  onChange={(e) => {
                                                    handleConditionChange(block.id, condition.id, 'column', e.target.value);
                                                  }}
                                                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                                >
                                                  <option value="">Selectionner...</option>
                                                  {allFields.map((col) => (
                                                    <option key={col} value={col}>{formatFieldLabel(col)}</option>
                                                  ))}
                                                </select>
                                              </div>
                                              {condition.column && (
                                                <div className="text-xs text-gray-500">
                                                  Type: <span className="font-semibold text-gray-700">{getFieldKind(condition.column)}</span>
                                                </div>
                                              )}
                                              {condition.column && getFieldKind(condition.column) === 'numeric' ? (
                                                <div className="grid grid-cols-2 gap-2">
                                                  <div>
                                                    <label className="block text-xs font-medium text-gray-600 mb-1">Min</label>
                                                    <input
                                                      type="number"
                                                      value={condition.min ?? ''}
                                                      onChange={(e) => handleConditionChange(block.id, condition.id, 'min', e.target.value)}
                                                      placeholder="Valeur min"
                                                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                                    />
                                                  </div>
                                                  <div>
                                                    <label className="block text-xs font-medium text-gray-600 mb-1">Max</label>
                                                    <input
                                                      type="number"
                                                      value={condition.max ?? ''}
                                                      onChange={(e) => handleConditionChange(block.id, condition.id, 'max', e.target.value)}
                                                      placeholder="Valeur max"
                                                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                                    />
                                                  </div>
                                                </div>
                                              ) : condition.column && valuesByField[condition.column] ? (
                                                <div>
                                                  <label className="block text-xs font-medium text-gray-600 mb-1">Valeur</label>
                                                  <div className="space-y-2 max-h-48 overflow-y-auto border border-gray-200 rounded-lg p-3">
                                                    {valuesByField[condition.column].map((modalite) => (
                                                      <label key={modalite} className="flex items-center gap-2 cursor-pointer">
                                                        <input
                                                          type="radio"
                                                          name={`filter-${condition.id}`}
                                                          checked={condition.values?.[0] === modalite}
                                                          onChange={() => handleConditionChange(block.id, condition.id, 'values', [modalite])}
                                                          className="w-4 h-4 text-pink-600 border-gray-300 focus:ring-pink-500"
                                                        />
                                                        <span className="text-sm text-gray-700">{modalite}</span>
                                                      </label>
                                                    ))}
                                                  </div>
                                                </div>
                                              ) : null}
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

            {/* Workflow Preview */}
            <WorkflowPreview
              blocks={blocks}
              getBlockDisplayNumber={getBlockDisplayNumber}
              onSelectBlock={handleWorkflowSelect}
              onAddChildBlock={handleWorkflowAddChild}
              modalOpen={isBlockModalOpen}
            />

            {/* Submit Buttons */}
            <div className="flex items-center justify-end gap-4 pt-6 border-t">
              <button
                type="button"
                onClick={() => navigate('/modeles')}
                className="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Annuler
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-6 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {createMutation.isPending
                  ? (isEditing ? 'Mise a jour...' : 'Creation...')
                  : (isEditing ? 'Mettre a jour le modele' : 'Creer le modele')}
              </button>
            </div>
          </div>
        </form>
      )}

      {isBlockModalOpen && selectedBlock && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={closeBlockModal}
        >
          <div
            className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl bg-white shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-gray-200 p-4">
              <div>
                <div className="text-xs text-gray-500">Bloc {selectedBlockNumber}</div>
                <h3 className="text-lg font-semibold text-gray-900">{selectedBlock.canal}</h3>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (selectedHasChildren) {
                      showDeleteBlockedToast();
                      return;
                    }
                    handleRemoveBlock(selectedBlock.id);
                    closeBlockModal();
                  }}
                  disabled={selectedHasChildren}
                  className="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" />
                  Supprimer
                </button>
                <button
                  type="button"
                  onClick={closeBlockModal}
                  className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                  aria-label="Close"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            <div className="space-y-4 p-4">
              {selectedBlock.parentBlockId !== null && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">
                    Bloc parent <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={selectedBlock.parentBlockId || ''}
                    onChange={(e) => handleBlockChange(selectedBlock.id, 'parentBlockId', e.target.value)}
                    disabled={true}
                    className="w-full cursor-not-allowed rounded-lg border border-gray-300 bg-gray-100 px-3 py-2 text-sm"
                  >
                    <option value="">Selectionner un bloc parent...</option>
                    {blocks
                      .filter(b => b.id !== selectedBlock.id)
                      .filter(b => !isDescendant(b.id, selectedBlock.id))
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
                <label className="mb-1 block text-xs font-medium text-gray-600">Canal</label>
                <select
                  value={selectedBlock.canal}
                  onChange={(e) => handleBlockChange(selectedBlock.id, 'canal', e.target.value)}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                >
                  {canauxData?.canaux.map((canal) => (
                    <option key={canal} value={canal}>
                      {canal}
                    </option>
                  ))}
                </select>
              </div>

              {(selectedBlock.canal === 'Mail' || selectedBlock.canal === 'EMAIL') && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Objet</label>
                  <input
                    type="text"
                    value={selectedBlock.objet || ''}
                    onChange={(e) => handleBlockChange(selectedBlock.id, 'objet', e.target.value)}
                    placeholder="Sujet de l'email"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                  />
                </div>
              )}

              {renderAntiSpamWarning(selectedBlock.canal)}

              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Contenu</label>
                <textarea
                  value={selectedBlock.contenu || ''}
                  onChange={(e) => handleBlockChange(selectedBlock.id, 'contenu', e.target.value)}
                  placeholder={
                    selectedBlock.canal === 'Mail' || selectedBlock.canal === 'EMAIL'
                      ? "Corps de l'email"
                      : selectedBlock.canal === 'SMS'
                      ? 'Message SMS'
                      : 'Message'
                  }
                  rows={4}
                  className="w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
              </div>

              {selectedBlock.parentBlockId !== null && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <GitBranch className="h-4 w-4 text-blue-600" />
                      <span className="text-sm font-medium text-blue-900">
                        Conditions (liees au bloc mere)
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => handleAddCondition(selectedBlock.id, 'days_since_last')}
                        className="rounded border border-blue-300 bg-white px-2 py-1 text-xs hover:bg-blue-50"
                      >
                        + NB jours depuis last action
                      </button>
                      <button
                        type="button"
                        onClick={() => handleAddCondition(selectedBlock.id, 'flag_resultat')}
                        className="rounded border border-blue-300 bg-white px-2 py-1 text-xs hover:bg-blue-50"
                      >
                        + Flag resultats
                      </button>
                      <button
                        type="button"
                        onClick={() => handleAddCondition(selectedBlock.id, 'counter')}
                        className="rounded border border-blue-300 bg-white px-2 py-1 text-xs hover:bg-blue-50"
                      >
                        + {(() => {
                          const parentBlock = blocks.find(b => b.id === selectedBlock.parentBlockId);
                          const parentCanal = parentBlock?.canal || selectedBlock.canal;
                          return canauxData?.compteur_by_canal[parentCanal] || 'NB_appel';
                        })()}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleAddCondition(selectedBlock.id, 'client_filter')}
                        className="rounded border border-blue-300 bg-white px-2 py-1 text-xs hover:bg-blue-50"
                      >
                        + Filtre client
                      </button>
                      <button
                        type="button"
                        onClick={() => handleAddCondition(selectedBlock.id, 'campaign_field')}
                        className="rounded border border-purple-300 bg-white px-2 py-1 text-xs hover:bg-purple-50"
                      >
                        + NB jours depuis début campagne
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {selectedBlock.conditions.length === 0 ? (
                      <div className="py-6 text-center text-sm text-gray-500">
                        Aucune condition. Cliquez sur un bouton ci-dessus pour ajouter une condition.
                      </div>
                    ) : (
                      selectedBlock.conditions.map((condition) => (
                        <div key={condition.id} className="rounded-lg border border-blue-200 bg-white p-3">
                          <div className="flex items-start gap-3">
                            <div className="flex-1">
                              {condition.type === 'days_since_last' && (
                                <div className="mb-2">
                                  <label className="mb-2 block text-sm font-semibold text-gray-800">
                                    NB jours depuis last action
                                  </label>
                                  <div className="grid grid-cols-2 gap-2">
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">Operateur</label>
                                      <select
                                        value={condition.operator || '='}
                                        onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'operator', e.target.value)}
                                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                      >
                                        <option value="=">=</option>
                                        <option value=">">{'>'}</option>
                                        <option value="<">{'<'}</option>
                                        <option value="<=">{'<='}</option>
                                        <option value=">=">{'>='}</option>
                                      </select>
                                    </div>
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">
                                        Valeur
                                      </label>
                                      <input
                                        type="number"
                                        value={condition.daysSinceLastAction || 1}
                                        onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'daysSinceLastAction', parseInt(e.target.value) || 1)}
                                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                        min="1"
                                      />
                                    </div>
                                  </div>
                                </div>
                              )}
                              {condition.type === 'flag_resultat' && (
                                <div className="mb-2">
                                  <label className="mb-2 block text-sm font-semibold text-gray-800">
                                    Flag resultats
                                  </label>
                                  <div className="grid grid-cols-2 gap-2">
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">Operateur</label>
                                      <select
                                        value="="
                                        disabled
                                        className="w-full rounded-lg border border-gray-300 bg-gray-100 px-3 py-2 text-sm"
                                      >
                                        <option value="=">=</option>
                                      </select>
                                    </div>
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">
                                        Valeur
                                      </label>
                                      <select
                                        value={condition.flagResultat || ''}
                                        onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'flagResultat', e.target.value)}
                                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                      >
                                        <option value="">Selectionner...</option>
                                        {(() => {
                                          const parentBlock = blocks.find(b => b.id === selectedBlock.parentBlockId);
                                          const parentCanal = parentBlock?.canal;
                                          const availableResultats = parentCanal
                                            ? (canauxData?.resultats_by_canal[parentCanal] || [])
                                            : [];

                                          return availableResultats.map((resultat) => (
                                            <option key={resultat} value={resultat}>
                                              {resultat}
                                            </option>
                                          ));
                                        })()}
                                      </select>
                                    </div>
                                  </div>
                                </div>
                              )}
                              {condition.type === 'counter' && (
                                <div className="mb-2">
                                  <label className="mb-2 block text-sm font-semibold text-gray-800">
                                    {(() => {
                                      const parentBlock = blocks.find(b => b.id === selectedBlock.parentBlockId);
                                      const parentCanal = parentBlock?.canal || selectedBlock.canal;
                                      return canauxData?.compteur_by_canal[parentCanal] || 'NB_appel';
                                    })()}
                                  </label>
                                  <div className="grid grid-cols-2 gap-2">
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">Operateur</label>
                                      <select
                                        value={condition.operator || '='}
                                        onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'operator', e.target.value)}
                                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                      >
                                        <option value="=">=</option>
                                        <option value=">">{'>'}</option>
                                        <option value="<">{'<'}</option>
                                        <option value="<=">{'<='}</option>
                                        <option value=">=">{'>='}</option>
                                      </select>
                                    </div>
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">
                                        Valeur
                                      </label>
                                      <input
                                        type="number"
                                        value={condition.counterValue || 1}
                                        onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'counterValue', parseInt(e.target.value) || 1)}
                                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                        min="1"
                                      />
                                    </div>
                                  </div>
                                </div>
                              )}
                              {condition.type === 'client_filter' && (
                                <div className="mb-2">
                                  <label className="mb-2 block text-sm font-semibold text-gray-800">
                                    Filtre client
                                  </label>
                                  <div className="space-y-3">
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">Colonne</label>
                                      <select
                                        value={condition.column || ''}
                                        onChange={(e) => {
                                          handleConditionChange(selectedBlock.id, condition.id, 'column', e.target.value);
                                        }}
                                        className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-xl text-gray-700"
                                      >
                                        <option value="">Selectionner...</option>
                                        {allFields.map((col) => (
                                          <option key={col} value={col}>{formatFieldLabel(col)}</option>
                                        ))}
                                      </select>
                                    </div>
                                    {condition.column && (
                                      <div className="text-xs text-gray-500">
                                        Type: <span className="font-semibold text-gray-700">{getFieldKind(condition.column)}</span>
                                      </div>
                                    )}
                                    {condition.column && getFieldKind(condition.column) === 'numeric' ? (
                                      <div className="grid grid-cols-2 gap-2">
                                        <div>
                                          <label className="mb-1 block text-xs font-medium text-gray-600">Min</label>
                                          <input
                                            type="number"
                                            value={condition.min ?? ''}
                                            onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'min', e.target.value)}
                                            placeholder="Valeur min"
                                            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                          />
                                        </div>
                                        <div>
                                          <label className="mb-1 block text-xs font-medium text-gray-600">Max</label>
                                          <input
                                            type="number"
                                            value={condition.max ?? ''}
                                            onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'max', e.target.value)}
                                            placeholder="Valeur max"
                                            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                          />
                                        </div>
                                      </div>
                                    ) : condition.column && valuesByField[condition.column] ? (
                                      <div>
                                        <label className="mb-1 block text-xs font-medium text-gray-600">Valeur</label>
                                        <div className="space-y-2 max-h-48 overflow-y-auto border border-gray-200 rounded-lg p-3">
                                          {valuesByField[condition.column].map((modalite) => (
                                            <label key={modalite} className="flex items-center gap-2 cursor-pointer">
                                              <input
                                                type="radio"
                                                name={`filter-${condition.id}`}
                                                checked={condition.values?.[0] === modalite}
                                                onChange={() => handleConditionChange(selectedBlock.id, condition.id, 'values', [modalite])}
                                                className="w-4 h-4 text-pink-600 border-gray-300 focus:ring-pink-500"
                                              />
                                              <span className="text-sm text-gray-700">{modalite}</span>
                                            </label>
                                          ))}
                                        </div>
                                      </div>
                                    ) : null}
                                  </div>
                                </div>
                              )}
                              {condition.type === 'campaign_field' && (
                                <div className="mb-2">
                                  <label className="mb-2 block text-sm font-semibold text-gray-800">
                                    {campaignConditionFields?.fields?.find(f => f.db_field === condition.campaignField)?.field || 'NB jours depuis début campagne'}
                                  </label>
                                  <div className="grid grid-cols-2 gap-2">
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">Opérateur</label>
                                      <select
                                        value={condition.operator || '='}
                                        onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'operator', e.target.value)}
                                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                      >
                                        <option value="=">=</option>
                                        <option value=">">{'>'}</option>
                                        <option value="<">{'<'}</option>
                                        <option value="<=">{'<='}</option>
                                        <option value=">=">{'>='}</option>
                                      </select>
                                    </div>
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-gray-600">
                                        Valeur (jours)
                                      </label>
                                      <input
                                        type="number"
                                        value={condition.campaignFieldValue ?? 0}
                                        onChange={(e) => handleConditionChange(selectedBlock.id, condition.id, 'campaignFieldValue', parseInt(e.target.value) || 0)}
                                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                        min="0"
                                      />
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={() => handleRemoveCondition(selectedBlock.id, condition.id)}
                              className="mt-1 rounded p-1 text-red-600 hover:bg-red-50"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

