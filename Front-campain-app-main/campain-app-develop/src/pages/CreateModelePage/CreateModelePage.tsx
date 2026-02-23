import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2, GitBranch, X, Eye, Code2, Undo2, Redo2, Copy } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { metaApi } from '@/lib/api/definitions/meta.api';
import { getApiClient } from '@/lib/api/api-client';
import LoadingSpinner from '../../components/LoadingSpinner';
import Toast from '../../components/Toast';
import WorkflowPreview from '../../components/custom/WorkflowPreview';
import ParentConditionsSection from '../../components/custom/ParentConditionsSection';
import ObjectiveConditionsSection from '../../components/custom/ObjectiveConditionsSection';
import type { CanauxMetadata, CampaignConditionField, EditPayload, DuplicateState, ConditionMetaResponse } from '@/types/modele.types';
import { useBlockManagement } from '@/hooks/useBlockManagement';
import { getBlockDepth, getBlockDisplayNumber, getOrderedBlocks, getHierarchicalNumber } from '@/lib/block-utils';
import { buildBlocksPayload } from '@/lib/modele-serialization';
import { formatFieldLabel, getFieldKind, isSpamSensitiveCanal, normalizeCanal, resolveBlocksFromPayload } from '@/lib/modele-normalization';

const areSameIdSets = (left: string[], right: string[]): boolean => {
  if (left.length !== right.length) return false;
  const rightSet = new Set(right);
  for (const id of left) {
    if (!rightSet.has(id)) return false;
  }
  return true;
};

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

  const [formData, setFormData] = useState({ nom_modele: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<{ sourceId: string; targetId: string } | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [bulkDelai, setBulkDelai] = useState<number>(0);
  const [bulkCanal, setBulkCanal] = useState<string>('');
  const [isBlockModalOpen, setIsBlockModalOpen] = useState(false);
  const scrollContainerRef = useRef<HTMLElement | null>(null);
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' | 'warning' }>({
    isOpen: false,
    title: '',
  });

  // Queries
  const { data: canauxData, isLoading: canauxLoading } = useQuery<CanauxMetadata>({
    queryKey: ['meta-canaux'],
    queryFn: () => apiClient.request<CanauxMetadata>(metaApi.getCanaux()),
  });

  const { data: conditionMeta, isLoading: conditionMetaLoading } = useQuery<ConditionMetaResponse>({
    queryKey: ['condition-meta'],
    queryFn: () => apiClient.request<ConditionMetaResponse>(metaApi.getConditionMeta()),
  });

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

  // Derived field data
  const { numFields, allFields, valuesByField } = useMemo(() => {
    if (!conditionMeta) return { numFields: [] as string[], allFields: [] as string[], valuesByField: {} as Record<string, string[]> };
    const numF: string[] = [];
    const catF: string[] = [];
    const vbf: Record<string, string[]> = {};
    Object.entries(conditionMeta).forEach(([field, value]) => {
      if (value === 'Numérique') numF.push(field);
      else if (Array.isArray(value)) { catF.push(field); vbf[field] = value; }
    });
    return { numFields: numF, allFields: [...catF, ...numF], valuesByField: vbf };
  }, [conditionMeta]);

  // Block management hook
  const bm = useBlockManagement(canauxData);

  // Anti-spam warning
  const renderAntiSpamWarning = (canal: string) => {
    if (!isSpamSensitiveCanal(canal)) return null;
    const label = normalizeCanal(canal) === 'sms' ? 'SMS' : 'Email';
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        <span className="font-semibold">Attention anti-spam ({label})</span>
        <span className="ml-2">Verifier consentement, identite expediteur et desabonnement.</span>
      </div>
    );
  };

  // Load edit/duplicate payload
  useEffect(() => { hasLoadedEdit.current = false; }, [sourceId]);

  useEffect(() => {
    if ((!isEditing && !isDuplicating) || !editPayload || hasLoadedEdit.current) return;
    hasLoadedEdit.current = true;
    const loadedBlocks = resolveBlocksFromPayload(editPayload);
    setFormData({ nom_modele: editPayload.nom_modele || '' });
    bm.setBlocks(loadedBlocks, { recordHistory: false, resetHistory: true });
    bm.setExpandedBlocks(new Set());
    setActiveBlockId(null);
    setSelectedNodeIds([]);
    setSelectedEdge(null);
    setErrors({});
  }, [editPayload, isEditing, isDuplicating]);

  // Auto-add first block
  useEffect(() => {
    if (!canauxLoading && !isEditing && !isDuplicating && bm.blocks.length === 0) {
      bm.handleAddBlock(null);
    }
  }, [canauxLoading, bm.blocks.length, isEditing, isDuplicating]);

  useEffect(() => {
    if (!scrollContainerRef.current) scrollContainerRef.current = document.querySelector('main');
  }, []);

  // Mutation
  const createMutation = useMutation({
    mutationFn: (data: any) => apiClient.request(modelesApi.save(data)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['modeles'] });
      setToast({ isOpen: true, title: 'Succes', message: isEditing ? 'Le modele a ete mis a jour avec succes' : 'Le modele a ete cree avec succes', type: 'success' });
      setTimeout(() => navigate('/modeles'), 1500);
    },
    onError: (error: any) => {
      console.error(isEditing ? 'Error updating modele:' : 'Error creating modele:', error);
      setToast({ isOpen: true, title: 'Erreur', message: isEditing ? 'Une erreur est survenue lors de la mise a jour' : 'Une erreur est survenue lors de la creation', type: 'error' });
    },
  });

  // Block modal handlers
  const openBlockModal = (blockId: string) => {
    setActiveBlockId(blockId);
    setIsBlockModalOpen(true);
    bm.setExpandedBlocks(prev => { const next = new Set(prev); next.add(blockId); return next; });
  };

  const closeBlockModal = useCallback(() => setIsBlockModalOpen(false), []);

  const handleWorkflowSelect = (blockId: string) => {
    setSelectedEdge(null);
    setSelectedNodeIds([blockId]);
    openBlockModal(blockId);
  };

  const handleWorkflowSelectionChange = (ids: string[]) => {
    setSelectedNodeIds(prev => (areSameIdSets(prev, ids) ? prev : ids));
    if (ids.length === 1) {
      const selectedId = ids[0];
      setActiveBlockId(prev => (prev === selectedId ? prev : selectedId));
      setSelectedEdge(prev => (prev ? null : prev));
      return;
    }
    if (ids.length === 0 && !selectedEdge) {
      setActiveBlockId(prev => (prev === null ? prev : null));
    }
  };

  const handleWorkflowAddChild = (parentId: string) => {
    const newBlockId = bm.handleAddBlock(parentId);
    setSelectedEdge(null);
    setSelectedNodeIds([newBlockId]);
    openBlockModal(newBlockId);
  };

  const handleWorkflowAddObjectiveChild = (parentId: string) => {
    const newBlockId = bm.handleAddBlock(parentId, true);
    setSelectedEdge(null);
    setSelectedNodeIds([newBlockId]);
    openBlockModal(newBlockId);
  };

  const handleLinkBlocks = (sourceId: string, targetId: string) => {
    const targetBlock = bm.blocks.find(b => b.id === targetId);
    if (!targetBlock) return;
    if (targetBlock.parents.includes(sourceId)) return;
    bm.handleAddParent(targetId, sourceId);
  };

  const removeEdgeFromGraph = (sourceId: string, targetId: string) => {
    bm.handleRemoveParent(targetId, sourceId);
    setSelectedEdge(prev => (
      prev && prev.sourceId === sourceId && prev.targetId === targetId ? null : prev
    ));
  };

  const duplicateBlock = (blockId: string) => {
    const sourceBlock = bm.blocks.find(b => b.id === blockId);
    if (!sourceBlock) return;

    const defaultCanal = canauxData?.canaux[0] || 'Appel';
    const newBlockId = `block_${Date.now()}`;
    const clonedObjectiveConditions = sourceBlock.objectiveConditions.map((cond, index) => ({
      ...cond,
      id: `cond_${Date.now()}_${index}`,
      nextBlockId: null,
    }));

    const newBlock: typeof sourceBlock = {
      id: newBlockId,
      canal: sourceBlock.isObjectif ? '' : (sourceBlock.canal || defaultCanal),
      delai: sourceBlock.delai,
      objet: sourceBlock.objet,
      contenu: sourceBlock.contenu,
      parents: [],
      conditionsByParent: {},
      isObjectif: sourceBlock.isObjectif,
      valideObjectif: sourceBlock.valideObjectif,
      objectiveConditions: clonedObjectiveConditions,
      objectiveOperator: sourceBlock.objectiveOperator,
    };

    bm.setBlocks(prev => [...prev, newBlock]);
    bm.setExpandedBlocks(prev => { const next = new Set(prev); next.add(newBlockId); return next; });

    setActiveBlockId(newBlockId);
    setSelectedNodeIds([newBlockId]);
    setSelectedEdge(null);
  };

  const removeBlockFromGraph = (blockId: string) => {
    const hasChildren = bm.blocks.some(b => b.parents.includes(blockId));
    if (hasChildren) {
      showDeleteBlockedToast();
      return;
    }
    bm.handleRemoveBlock(blockId);
    if (activeBlockId === blockId) setActiveBlockId(null);
    setSelectedNodeIds(prev => prev.filter(id => id !== blockId));
    setSelectedEdge(prev => (prev && (prev.sourceId === blockId || prev.targetId === blockId)) ? null : prev);
  };

  const removeBlocksFromGraph = (ids: string[]) => {
    if (ids.length === 0) return;
    const selectedSet = new Set(ids);
    const hasExternalChildren = bm.blocks.some(block =>
      !selectedSet.has(block.id) && block.parents.some(pid => selectedSet.has(pid))
    );

    if (hasExternalChildren) {
      showDeleteBlockedToast();
      return;
    }

    bm.setBlocks(prev => {
      const updatedBlocks = prev.filter(block => !selectedSet.has(block.id));
      return updatedBlocks.map(block => {
        const newParents = block.parents.filter(pid => !selectedSet.has(pid));
        const newCondsByParent = { ...block.conditionsByParent };
        ids.forEach(id => { delete newCondsByParent[id]; });

        const cleanedCondsByParent: Record<string, any[]> = {};
        for (const [pid, conds] of Object.entries(newCondsByParent)) {
          if (!newParents.includes(pid)) continue;
          cleanedCondsByParent[pid] = conds.map(cond => ({
            ...cond,
            nextBlockId: cond.nextBlockId && selectedSet.has(cond.nextBlockId) ? null : cond.nextBlockId,
          }));
        }

        return { ...block, parents: newParents, conditionsByParent: cleanedCondsByParent };
      });
    });

    setSelectedNodeIds([]);
    setSelectedEdge(null);
    setActiveBlockId(null);
  };

  const showDeleteBlockedToast = () => {
    setToast({ isOpen: true, title: 'Suppression impossible', message: 'Ce bloc a des blocs enfants. Supprimez d abord les enfants.', type: 'warning' });
  };

  // Auto-scroll
  useEffect(() => {
    const sc = scrollContainerRef.current || document.querySelector('main');
    if (!sc || isBlockModalOpen) return;
    requestAnimationFrame(() => { sc.scrollTop = sc.scrollHeight; });
    setTimeout(() => { sc.scrollTop = sc.scrollHeight; }, 80);
  }, [isBlockModalOpen]);

  // Escape key for modal
  useEffect(() => {
    if (!isBlockModalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') closeBlockModal(); };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [closeBlockModal, isBlockModalOpen]);

  useEffect(() => {
    if (!selectedEdge) return;
    const targetBlock = bm.blocks.find(block => block.id === selectedEdge.targetId);
    if (!targetBlock || !targetBlock.parents.includes(selectedEdge.sourceId)) {
      setSelectedEdge(null);
    }
  }, [bm.blocks, selectedEdge]);

  // Submit
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Record<string, string> = {};

    if (!formData.nom_modele.trim()) newErrors.nom_modele = 'Le nom du modele est requis';
    if (bm.blocks.length === 0) newErrors.blocks = 'Au moins une action est requise';



    if (Object.keys(newErrors).length > 0) { setErrors(newErrors); return; }

    const { serializedBlocks } = buildBlocksPayload(bm.blocks, canauxData);

    createMutation.mutate({
      is_editing: isEditing,
      id_modele: isEditing ? (id || '') : '',
      nom_modele: formData.nom_modele,
      variable_cible: '',
      objectif_value_for_store: '',
      blocks: serializedBlocks,
    });
  };

  // Derived state
  const isMetaLoading = canauxLoading || conditionMetaLoading || ((isEditing || isDuplicating) && editLoading);
  const selectedBlock = useMemo(() => activeBlockId ? bm.blocks.find(b => b.id === activeBlockId) : null, [activeBlockId, bm.blocks]);
  const selectedBlockNumber = selectedBlock ? getHierarchicalNumber(bm.blocks, selectedBlock.id) : '';
  const selectedHasChildren = selectedBlock ? bm.blocks.some(b => b.parents.includes(selectedBlock.id)) : false;
  const selectedAvailableParents = useMemo(() => {
    if (!selectedBlock) return [];
    return bm.blocks
      .filter(b => b.id !== selectedBlock.id)
      .filter(b => !selectedBlock.parents.includes(b.id))
  }, [bm.blocks, selectedBlock]);
  const selectedEdgeContext = useMemo(() => {
    if (!selectedEdge) return null;
    const targetBlock = bm.blocks.find(b => b.id === selectedEdge.targetId);
    const parentBlock = bm.blocks.find(b => b.id === selectedEdge.sourceId);
    if (!targetBlock || !parentBlock) return null;

    return {
      targetBlock,
      parentBlock,
      blockForEditor: {
        ...targetBlock,
        parents: [selectedEdge.sourceId],
        conditionsByParent: {
          [selectedEdge.sourceId]: targetBlock.conditionsByParent[selectedEdge.sourceId] || [],
        },
      },
    };
  }, [bm.blocks, selectedEdge]);

  const selectedNodeSet = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds]);

  const applyBulkDelay = () => {
    if (selectedNodeIds.length <= 1) return;
    bm.setBlocks(prev => prev.map(block =>
      selectedNodeSet.has(block.id) ? { ...block, delai: Math.max(0, Number(bulkDelai) || 0) } : block
    ));
  };

  const applyBulkCanal = () => {
    if (selectedNodeIds.length <= 1 || !bulkCanal) return;
    bm.setBlocks(prev => prev.map(block =>
      selectedNodeSet.has(block.id) && !block.isObjectif ? { ...block, canal: bulkCanal } : block
    ));
  };

  const liveValidation = useMemo(() => {
    const blockWarnings: Record<string, number> = {};
    const edgeWarnings: Record<string, number> = {};

    for (const block of bm.blocks) {
      let warningCount = 0;

      if (block.isObjectif) {
        if (block.objectiveConditions.length === 0) warningCount += 1;
      } else {
        if (!block.canal.trim()) warningCount += 1;
        if ((block.canal === 'Mail' || block.canal === 'EMAIL') && !(block.objet || '').trim()) warningCount += 1;
        if (!(block.contenu || '').trim()) warningCount += 1;
      }

      for (const parentId of block.parents) {
        const condCount = (block.conditionsByParent[parentId] || []).length;
        if (condCount === 0) {
          edgeWarnings[`${parentId}->${block.id}`] = 1;
          warningCount += 1;
        }
      }

      if (warningCount > 0) blockWarnings[block.id] = warningCount;
    }

    return { blockWarnings, edgeWarnings };
  }, [bm.blocks]);

  const ordered = getOrderedBlocks(bm.blocks);

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
      <Toast isOpen={toast.isOpen} onClose={() => setToast({ ...toast, isOpen: false })} title={toast.title} message={toast.message} type={toast.type} />

      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <button onClick={() => navigate('/modeles')} className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors">
          <ArrowLeft className="w-5 h-5" /> <span>Retour aux modeles</span>
        </button>
        <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">{isEditing ? 'Modifier le modele' : 'Nouveau modele'}</h1>
        <p className="text-gray-600 mt-2">{isEditing ? 'Modifiez le modele de campagne avec des actions et des conditions' : 'Creez un nouveau modele de campagne avec des actions et des conditions'}</p>
      </div>

      {isMetaLoading ? (
        <div className="flex items-center justify-center py-20"><LoadingSpinner size="lg" /></div>
      ) : (
        <form onSubmit={handleSubmit} className="max-w-7xl mx-auto">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-6">
            {/* Model name */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Nom du modele <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  value={formData.nom_modele}
                  onChange={(e) => setFormData({ ...formData, nom_modele: e.target.value })}
                  className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent ${errors.nom_modele ? 'border-red-500' : 'border-gray-300'}`}
                  placeholder="Ex: Campagne de relance"
                />
                {errors.nom_modele && <p className="mt-1 text-sm text-red-500">{errors.nom_modele}</p>}
              </div>
            </div>

            {/* Workflow Tabs */}
            <Tabs defaultValue="visual" className="border-t pt-6">
              <div className="flex items-center justify-between mb-4">
                <TabsList>
                  <TabsTrigger value="visual" className="flex items-center gap-1.5">
                    <Eye className="w-4 h-4" /> Visuel
                  </TabsTrigger>
                  <TabsTrigger value="editor" className="flex items-center gap-1.5">
                    <Code2 className="w-4 h-4" /> Editeur
                  </TabsTrigger>
                </TabsList>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={bm.undo}
                    disabled={!bm.canUndo}
                    className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                    title="Annuler"
                  >
                    <Undo2 className="w-3.5 h-3.5" /> Undo
                  </button>
                  <button
                    type="button"
                    onClick={bm.redo}
                    disabled={!bm.canRedo}
                    className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                    title="Retablir"
                  >
                    <Redo2 className="w-3.5 h-3.5" /> Redo
                  </button>
                  <button type="button" onClick={() => { const id = bm.handleAddBlock(null, false); setSelectedNodeIds([id]); setSelectedEdge(null); openBlockModal(id); }} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700 flex items-center gap-1.5 font-medium">
                    <Plus className="w-3.5 h-3.5" /> Action
                  </button>
                </div>
              </div>

              {errors.blocks && <p className="mb-2 text-sm text-red-500">{errors.blocks}</p>}

              {/* Visual tab - workflow graph */}
              <TabsContent value="visual">
                {bm.blocks.length === 0 ? (
                  <div className="p-8 border-2 border-dashed border-gray-300 rounded-lg text-center">
                    <GitBranch className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                    <p className="text-gray-500 mb-4">Aucune action ajoutee. Commencez a construire votre workflow.</p>
                  </div>
                ) : (
                  <WorkflowPreview
                    blocks={bm.blocks}
                    getBlockDisplayNumber={(blockId: string) => getBlockDisplayNumber(bm.blocks, blockId)}
                    onSelectBlock={handleWorkflowSelect}
                    onAddChildBlock={handleWorkflowAddChild}
                    onAddObjectiveChildBlock={handleWorkflowAddObjectiveChild}
                    onDuplicateBlock={duplicateBlock}
                    onDeleteBlock={removeBlockFromGraph}
                    onDeleteEdge={removeEdgeFromGraph}
                    onLinkBlocks={handleLinkBlocks}
                    selectedBlockIds={selectedNodeIds}
                    blockValidation={liveValidation.blockWarnings}
                    edgeValidation={liveValidation.edgeWarnings}
                    showHeader={false}
                    showFrame={false}
                    height="calc(100vh - 280px)"
                    containerClassName="rounded-lg border border-gray-200"
                  />
                )}
              </TabsContent>

              {/* Editor tab - block list */}
              <TabsContent value="editor">
                {bm.blocks.length === 0 ? (
                  <div className="p-8 border-2 border-dashed border-gray-300 rounded-lg text-center">
                    <GitBranch className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                    <p className="text-gray-500 mb-4">Aucune action ajoutee. Utilisez les boutons ci-dessus pour commencer.</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {ordered.map((block) => {
                      const depth = getBlockDepth(bm.blocks, block.id);
                      const hierarchicalNumber = getHierarchicalNumber(bm.blocks, block.id);
                      const isChildBlock = block.parents.length > 0;
                      const isExpanded = bm.expandedBlocks.has(block.id);
                      const totalConditionCount = Object.values(block.conditionsByParent).reduce((sum, c) => sum + c.length, 0);
                      const conditionLabel = totalConditionCount === 1 ? 'condition' : 'conditions';
                      const availableParents = bm.blocks
                        .filter(b => b.id !== block.id)
                        .filter(b => !block.parents.includes(b.id))

                      return (
                        <div key={block.id} className="border border-gray-300 rounded-lg bg-white overflow-hidden" style={{ marginLeft: `${depth * 2}rem` }}>
                          <div className="p-4 bg-gray-50 border-b border-gray-200">
                            <div className={`flex items-center justify-between ${isExpanded ? 'mb-4' : ''}`}>
                              <div className="flex items-center gap-3 flex-1">
                                <span className="flex items-center justify-center w-8 h-8 bg-slate-900 text-white rounded-full text-sm font-bold">{hierarchicalNumber}</span>
                                <div className="flex-1">
                                  <div className="text-sm font-semibold text-gray-900">{block.isObjectif ? 'Bloc Objectif' : `Canal: ${block.canal}`}</div>
                                  <div className="text-xs text-gray-600">
                                    <span>Delai: {block.delai}</span>
                                    {isChildBlock && <span className="ml-2">- {totalConditionCount} {conditionLabel}</span>}
                                  </div>
                                  <div className={`mt-3 space-y-3 ${isExpanded ? '' : 'hidden'}`}>
                                    {(block.parents.length > 0 || availableParents.length > 0) && (
                                      <div>
                                        <label className="block text-xs font-medium text-gray-600 mb-1">Parents</label>
                                        <div className="flex flex-wrap gap-1">
                                          {block.parents.map(pid => {
                                            const parentBlock = bm.blocks.find(b => b.id === pid);
                                            const parentNum = getBlockDisplayNumber(bm.blocks, pid);
                                            return (
                                              <span key={pid} className="inline-flex items-center gap-1 px-2 py-1 bg-gray-200 rounded text-xs">
                                                Bloc {parentNum} - {parentBlock?.isObjectif ? 'Objectif' : (parentBlock?.canal || '?')}
                                                <button type="button" onClick={() => bm.handleRemoveParent(block.id, pid)} className="text-gray-500 hover:text-red-500"><X className="w-3 h-3" /></button>
                                              </span>
                                            );
                                          })}
                                          <select value="" onChange={(e) => { if (e.target.value) bm.handleAddParent(block.id, e.target.value); }} className="px-2 py-1 border border-dashed border-gray-300 rounded text-xs">
                                            <option value="">+ Parent</option>
                                            {availableParents
                                              .map(b => <option key={b.id} value={b.id}>Bloc {getBlockDisplayNumber(bm.blocks, b.id)} - {b.isObjectif ? 'Objectif' : b.canal}</option>)}
                                          </select>
                                        </div>
                                      </div>
                                    )}

                                    {block.parents.some(pid => bm.blocks.find(b => b.id === pid)?.isObjectif) && (
                                      <div>
                                        <label className="block text-xs font-medium text-gray-600 mb-1">Valide objectif</label>
                                        <div className="flex gap-4">
                                          {(['Oui', 'Non'] as const).map(val => (
                                            <label key={val} className="flex items-center gap-1.5 text-xs cursor-pointer">
                                              <input
                                                type="radio"
                                                checked={(block.valideObjectif ?? 'Non') === val}
                                                onChange={() => bm.handleBlockChange(block.id, 'valideObjectif', val)}
                                              />
                                              {val}
                                            </label>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {!block.isObjectif && (
                                      <>
                                        <div>
                                          <label className="block text-xs font-medium text-gray-600 mb-1">Canal</label>
                                          <select value={block.canal} onChange={(e) => bm.handleBlockChange(block.id, 'canal', e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 bg-white">
                                            {canauxData?.canaux.map((canal) => <option key={canal} value={canal}>{canal}</option>)}
                                          </select>
                                        </div>
                                        {(block.canal === 'Mail' || block.canal === 'EMAIL') && (
                                          <div>
                                            <label className="block text-xs font-medium text-gray-600 mb-1">Objet</label>
                                            <input type="text" value={block.objet || ''} onChange={(e) => bm.handleBlockChange(block.id, 'objet', e.target.value)} placeholder="Sujet de l'email" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
                                          </div>
                                        )}
                                        {renderAntiSpamWarning(block.canal)}
                                        <div>
                                          <label className="block text-xs font-medium text-gray-600 mb-1">Contenu</label>
                                          <textarea value={block.contenu || ''} onChange={(e) => bm.handleBlockChange(block.id, 'contenu', e.target.value)} placeholder={block.canal === 'Mail' || block.canal === 'EMAIL' ? "Corps de l'email" : block.canal === 'SMS' ? 'Message SMS' : 'Message'} rows={3} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none" />
                                        </div>
                                      </>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <button type="button" onClick={() => bm.handleAddBlock(block.id, false)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors flex items-center gap-1" title="Ajouter une action enfant">
                                <Plus className="w-3 h-3" /> Action
                              </button>
                              <button type="button" onClick={() => bm.handleAddBlock(block.id, true)} className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 transition-colors flex items-center gap-1" title="Ajouter un objectif enfant">
                                <Plus className="w-3 h-3" /> Objectif
                              </button>
                              <button type="button" onClick={() => bm.toggleBlockExpanded(block.id)} className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors">
                                {isExpanded ? 'Reduire' : 'Details'}
                              </button>
                              <button type="button" onClick={() => { const hasChildren = bm.blocks.some(b => b.parents.includes(block.id)); if (hasChildren) showDeleteBlockedToast(); else bm.handleRemoveBlock(block.id); }} className="p-2 text-red-600 hover:bg-red-50 rounded transition-colors" title="Supprimer le bloc">
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>

                          {isExpanded && isChildBlock && (
                            <ParentConditionsSection
                              block={block}
                              blocks={bm.blocks}
                              canauxData={canauxData}
                              campaignConditionFields={campaignConditionFields}
                              allFields={allFields}
                              numFields={numFields}
                              valuesByField={valuesByField}
                              onAddCondition={bm.handleAddCondition}
                              onRemoveCondition={bm.handleRemoveCondition}
                              onConditionChange={bm.handleConditionChange}
                              formatFieldLabel={formatFieldLabel}
                              getFieldKind={(col) => getFieldKind(col, numFields)}
                            />
                          )}

                          {isExpanded && block.isObjectif && (
                            <ObjectiveConditionsSection
                              block={block}
                              allFields={allFields}
                              numFields={numFields}
                              valuesByField={valuesByField}
                              onBlockChange={bm.handleBlockChange}
                              onAddObjectiveCondition={bm.handleAddObjectiveCondition}
                              onRemoveObjectiveCondition={bm.handleRemoveObjectiveCondition}
                              onObjectiveConditionChange={bm.handleObjectiveConditionChange}
                              formatFieldLabel={formatFieldLabel}
                              getFieldKind={(col) => getFieldKind(col, numFields)}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>
            </Tabs>

            {/* Submit */}
            <div className="flex items-center justify-end gap-4 pt-4 border-t border-gray-200">
              <button type="button" onClick={() => navigate('/modeles')} className="px-6 py-3 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors font-medium">Annuler</button>
              <button type="submit" disabled={createMutation.isPending} className="px-6 py-3 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2">
                {createMutation.isPending && <LoadingSpinner size="sm" />}
                {createMutation.isPending ? (isEditing ? 'Mise a jour...' : 'Creation...') : (isEditing ? 'Mettre a jour le modele' : 'Creer le modele')}
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Block Detail Modal */}
      {isBlockModalOpen && selectedBlock && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={closeBlockModal}>
          <div className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl bg-white shadow-lg" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-gray-200 p-4">
              <div>
                <div className="text-xs text-gray-500">Bloc {selectedBlockNumber}</div>
                <h3 className="text-lg font-semibold text-gray-900">{selectedBlock.isObjectif ? 'Bloc Objectif' : selectedBlock.canal}</h3>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => { if (selectedHasChildren) { showDeleteBlockedToast(); return; } bm.handleRemoveBlock(selectedBlock.id); closeBlockModal(); }} disabled={selectedHasChildren} className="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50">
                  <Trash2 className="h-4 w-4" /> Supprimer
                </button>
                <button type="button" onClick={closeBlockModal} className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700" aria-label="Close">
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            <div className="space-y-4 p-4">
              {/* Parents management */}
              {(selectedBlock.parents.length > 0 || selectedAvailableParents.length > 0) && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Parents</label>
                  <div className="flex flex-wrap gap-1">
                    {selectedBlock.parents.map(pid => {
                      const parentBlock = bm.blocks.find(b => b.id === pid);
                      const parentNum = getBlockDisplayNumber(bm.blocks, pid);
                      return (
                        <span key={pid} className="inline-flex items-center gap-1 rounded bg-gray-200 px-2 py-1 text-xs">
                          Bloc {parentNum} - {parentBlock?.isObjectif ? 'Objectif' : (parentBlock?.canal || '?')}
                          <button type="button" onClick={() => bm.handleRemoveParent(selectedBlock.id, pid)} className="text-gray-500 hover:text-red-500"><X className="h-3 w-3" /></button>
                        </span>
                      );
                    })}
                    <select value="" onChange={(e) => { if (e.target.value) bm.handleAddParent(selectedBlock.id, e.target.value); }} className="rounded border border-dashed border-gray-300 px-2 py-1 text-xs">
                      <option value="">+ Parent</option>
                      {selectedAvailableParents
                        .map(b => <option key={b.id} value={b.id}>Bloc {getBlockDisplayNumber(bm.blocks, b.id)} - {b.isObjectif ? 'Objectif' : b.canal}</option>)}
                    </select>
                  </div>
                </div>
              )}

              {/* Valide objectif */}
              {selectedBlock.parents.some(pid => bm.blocks.find(b => b.id === pid)?.isObjectif) && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Valide objectif</label>
                  <div className="flex gap-4">
                    {(['Oui', 'Non'] as const).map(val => (
                      <label key={val} className="flex items-center gap-1.5 text-sm cursor-pointer">
                        <input
                          type="radio"
                          checked={(selectedBlock.valideObjectif ?? 'Non') === val}
                          onChange={() => bm.handleBlockChange(selectedBlock.id, 'valideObjectif', val)}
                        />
                        {val}
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Canal/Objet/Contenu for action blocks */}
              {!selectedBlock.isObjectif && (
                <>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">Canal</label>
                    <select value={selectedBlock.canal} onChange={(e) => bm.handleBlockChange(selectedBlock.id, 'canal', e.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
                      {canauxData?.canaux.map((canal) => <option key={canal} value={canal}>{canal}</option>)}
                    </select>
                  </div>
                  {(selectedBlock.canal === 'Mail' || selectedBlock.canal === 'EMAIL') && (
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">Objet</label>
                      <input type="text" value={selectedBlock.objet || ''} onChange={(e) => bm.handleBlockChange(selectedBlock.id, 'objet', e.target.value)} placeholder="Sujet de l'email" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
                    </div>
                  )}
                  {renderAntiSpamWarning(selectedBlock.canal)}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">Contenu</label>
                    <textarea value={selectedBlock.contenu || ''} onChange={(e) => bm.handleBlockChange(selectedBlock.id, 'contenu', e.target.value)} placeholder={selectedBlock.canal === 'Mail' || selectedBlock.canal === 'EMAIL' ? "Corps de l'email" : selectedBlock.canal === 'SMS' ? 'Message SMS' : 'Message'} rows={4} className="w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
                  </div>
                </>
              )}

              {/* Parent conditions (blue) */}
              {selectedBlock.parents.length > 0 && (
                <ParentConditionsSection
                  block={selectedBlock}
                  blocks={bm.blocks}
                  canauxData={canauxData}
                  campaignConditionFields={campaignConditionFields}
                  allFields={allFields}
                  numFields={numFields}
                  valuesByField={valuesByField}
                  onAddCondition={bm.handleAddCondition}
                  onRemoveCondition={bm.handleRemoveCondition}
                  onConditionChange={bm.handleConditionChange}
                  formatFieldLabel={formatFieldLabel}
                  getFieldKind={(col) => getFieldKind(col, numFields)}
                />
              )}

              {/* Objective conditions (green) */}
              <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                <div className="flex items-center justify-between mb-3">
                  <label className="flex items-center gap-2 text-sm font-medium text-green-900">
                    <input type="checkbox" checked={selectedBlock.isObjectif} onChange={(e) => bm.handleBlockChange(selectedBlock.id, 'isObjectif', e.target.checked)} className="h-4 w-4 rounded border-gray-300 text-green-600" />
                    Bloc objectif
                  </label>
                </div>
                {selectedBlock.isObjectif && (
                  <ObjectiveConditionsSection
                    block={selectedBlock}
                    allFields={allFields}
                    numFields={numFields}
                    valuesByField={valuesByField}
                    onBlockChange={bm.handleBlockChange}
                    onAddObjectiveCondition={bm.handleAddObjectiveCondition}
                    onRemoveObjectiveCondition={bm.handleRemoveObjectiveCondition}
                    onObjectiveConditionChange={bm.handleObjectiveConditionChange}
                    formatFieldLabel={formatFieldLabel}
                    getFieldKind={(col) => getFieldKind(col, numFields)}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
