import { useState, useEffect } from 'react';
import { X, Plus, Trash2, GitBranch } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { metaApi } from '@/lib/api/definitions/meta.api';
import { getApiClient } from '@/lib/api/api-client';
import LoadingSpinner from '../LoadingSpinner';
import Toast from '../Toast';
import type { CanauxMetadata, CampaignConditionField } from '@/types/modele.types';
import { useBlockManagement } from '@/hooks/useBlockManagement';
import { getBlockDepth, getBlockDisplayNumber, getOrderedBlocks } from '@/lib/block-utils';
import { buildBlocksPayload } from '@/lib/modele-serialization';
import ParentConditionsSection from './ParentConditionsSection';
import ObjectiveConditionsSection from './ObjectiveConditionsSection';
import { formatFieldLabel, getFieldKind } from '@/lib/modele-normalization';

interface CreateModeleModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export default function CreateModeleModal({ isOpen, onClose, onSuccess }: CreateModeleModalProps) {
  const apiClient = getApiClient();
  const queryClient = useQueryClient();

  const [formData, setFormData] = useState({ nom_modele: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [toast, setToast] = useState<{ isOpen: boolean; title: string; message?: string; type?: 'success' | 'error' | 'warning' }>({
    isOpen: false,
    title: '',
  });

  const { data: canauxData, isLoading: canauxLoading } = useQuery<CanauxMetadata>({
    queryKey: ['meta-canaux'],
    queryFn: () => apiClient.request<CanauxMetadata>(metaApi.getCanaux()),
    enabled: isOpen,
  });

  const { data: campaignConditionFields } = useQuery<{ fields: CampaignConditionField[] }>({
    queryKey: ['campaign-condition-fields'],
    queryFn: () => apiClient.request<{ fields: CampaignConditionField[] }>(metaApi.getCampaignConditionFields()),
    enabled: isOpen,
  });

  // Fetch condition metadata for field kinds
  const { data: conditionMeta } = useQuery({
    queryKey: ['condition-meta'],
    queryFn: () => apiClient.request(metaApi.getConditionMeta()),
    enabled: isOpen,
  });

  const conditionMetaTyped = conditionMeta as Record<string, string[] | 'Numérique'> | undefined;
  const numFields: string[] = [];
  const allFields: string[] = [];
  const valuesByField: Record<string, string[]> = {};
  if (conditionMetaTyped) {
    const catFields: string[] = [];
    Object.entries(conditionMetaTyped).forEach(([field, value]) => {
      if (value === 'Numérique') {
        numFields.push(field);
      } else if (Array.isArray(value)) {
        catFields.push(field);
        valuesByField[field] = value;
      }
    });
    allFields.push(...catFields, ...numFields);
  }

  const bm = useBlockManagement(canauxData);

  const createMutation = useMutation({
    mutationFn: (data: any) => apiClient.request(modelesApi.save(data)),
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
    setFormData({ nom_modele: '' });
    bm.setBlocks([]);
    bm.setExpandedBlocks(new Set());
    setErrors({});
  };

  const handleClose = () => {
    resetForm();
    onClose();
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
    if (bm.blocks.length === 0) {
      newErrors.blocks = 'Au moins une action est requise';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    const { serializedBlocks } = buildBlocksPayload(bm.blocks, canauxData);

    createMutation.mutate({
      is_editing: false,
      id_modele: '',
      nom_modele: formData.nom_modele,
      variable_cible: '',
      objectif_value_for_store: '',
      blocks: serializedBlocks,
    });
  };

  useEffect(() => {
    if (isOpen) {
      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === 'Escape') handleClose();
      };
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const ordered = getOrderedBlocks(bm.blocks);

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
          <button onClick={handleClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors" aria-label="Close">
            <X className="w-6 h-6 text-gray-600" />
          </button>
        </div>

        {canauxLoading ? (
          <div className="p-12 text-center">
            <LoadingSpinner size="lg" />
            <p className="text-gray-500 mt-4">Chargement des métadonnées...</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-6">
            {/* Model name */}
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
                className={`w-full px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 ${errors.nom_modele ? 'border-red-500' : 'border-gray-300'}`}
                placeholder="Ex: Modèle Activation Carte"
              />
              {errors.nom_modele && <p className="mt-1 text-sm text-red-500">{errors.nom_modele}</p>}
            </div>

            {/* Workflow */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Workflow <span className="text-red-500">*</span></label>
                  <p className="text-xs text-gray-500 mt-1">Construisez votre workflow avec des actions et des conditions</p>
                </div>
                <div className="flex items-center gap-2">
                  <button type="button" onClick={() => bm.handleAddBlock(null, false)} className="px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-2 text-sm">
                    <Plus className="w-4 h-4" /> Action
                  </button>
                  <button type="button" onClick={() => bm.handleAddBlock(null, true)} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors flex items-center gap-2 text-sm">
                    <Plus className="w-4 h-4" /> Objectif
                  </button>
                </div>
              </div>

              {bm.blocks.length === 0 ? (
                <div className="p-8 border-2 border-dashed border-gray-300 rounded-lg text-center">
                  <GitBranch className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500">Aucune action ajoutée. Commencez à construire votre workflow.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {ordered.map((block) => {
                    const depth = getBlockDepth(bm.blocks, block.id);
                    const blockNumber = getBlockDisplayNumber(bm.blocks, block.id);
                    const availableParents = bm.blocks
                      .filter(b => b.id !== block.id)
                      .filter(b => !block.parents.includes(b.id))

                    return (
                      <div key={block.id} className="border border-gray-300 rounded-lg bg-white overflow-hidden" style={{ marginLeft: `${depth * 2}rem` }}>
                        <div className="p-4 bg-gray-50 border-b border-gray-200">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3 flex-1">
                              <span className="flex items-center justify-center w-8 h-8 bg-slate-900 text-white rounded-full text-sm font-bold">{blockNumber}</span>
                              <div className="flex-1 space-y-3">
                                {/* Parent selector */}
                                {(block.parents.length > 0 || availableParents.length > 0) && (
                                  <div>
                                    <label className="block text-xs font-medium text-gray-600 mb-1">Blocs parents</label>
                                    {block.parents.map((pid, pidx) => (
                                      <div key={pidx} className="flex items-center gap-2 mb-1">
                                        <select
                                          value={pid}
                                          onChange={(e) => {
                                            const newParents = [...block.parents];
                                            const oldPid = newParents[pidx];
                                            newParents[pidx] = e.target.value;
                                            const newCondsByParent = { ...block.conditionsByParent };
                                            const oldConds = newCondsByParent[oldPid] || [];
                                            delete newCondsByParent[oldPid];
                                            newCondsByParent[e.target.value] = oldConds;
                                            bm.setBlocks(bm.blocks.map(b => b.id === block.id ? { ...b, parents: newParents, conditionsByParent: newCondsByParent } : b));
                                          }}
                                          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 bg-white"
                                        >
                                          {bm.blocks
                                            .filter(b => b.id !== block.id)
                                            .map((b) => (
                                              <option key={b.id} value={b.id}>Bloc {getBlockDisplayNumber(bm.blocks, b.id)} - {b.canal || 'Objectif'}</option>
                                            ))}
                                        </select>
                                        {block.parents.length > 1 && (
                                          <button type="button" onClick={() => bm.handleRemoveParent(block.id, pid)} className="p-1 text-red-500 hover:bg-red-50 rounded" title="Retirer ce parent">
                                            <Trash2 className="w-3 h-3" />
                                          </button>
                                        )}
                                      </div>
                                    ))}
                                    <button
                                      type="button"
                                      onClick={() => {
                                        if (availableParents.length === 0) return;
                                        bm.handleAddParent(block.id, availableParents[0].id);
                                      }}
                                      className="mt-1 px-2 py-1 text-xs bg-gray-100 border border-gray-300 rounded hover:bg-gray-200 transition-colors"
                                    >
                                      + Ajouter un parent
                                    </button>
                                  </div>
                                )}

                                {/* Canal/Objet/Contenu for action blocks */}
                                {!block.isObjectif && (
                                  <>
                                    <div>
                                      <label className="block text-xs font-medium text-gray-600 mb-1">Canal</label>
                                      <select value={block.canal} onChange={(e) => bm.handleBlockChange(block.id, 'canal', e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 bg-white">
                                        {canauxData?.canaux.map((canal) => <option key={canal} value={canal}>{canal}</option>)}
                                      </select>
                                    </div>
                                    {block.canal === 'EMAIL' && (
                                      <div>
                                        <label className="block text-xs font-medium text-gray-600 mb-1">Objet</label>
                                        <input type="text" value={block.objet || ''} onChange={(e) => bm.handleBlockChange(block.id, 'objet', e.target.value)} placeholder="Sujet de l'email" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
                                      </div>
                                    )}
                                    <div>
                                      <label className="block text-xs font-medium text-gray-600 mb-1">Contenu</label>
                                      <textarea value={block.contenu || ''} onChange={(e) => bm.handleBlockChange(block.id, 'contenu', e.target.value)} placeholder={block.canal === 'EMAIL' ? "Corps de l'email" : block.canal === 'SMS' ? 'Message SMS' : 'Message'} rows={3} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none" />
                                    </div>
                                  </>
                                )}

                                {/* Objectif toggle */}
                                <div className={`rounded-lg border p-3 ${block.isObjectif ? 'border-green-300 bg-green-50' : 'border-gray-200 bg-gray-50'}`}>
                                  <label className="flex items-center gap-2 text-xs font-medium text-gray-700">
                                    <input type="checkbox" checked={block.isObjectif} onChange={(e) => bm.handleBlockChange(block.id, 'isObjectif', e.target.checked)} className="h-4 w-4 rounded border-gray-300 text-green-600" />
                                    Bloc objectif
                                  </label>
                                </div>
                              </div>
                            </div>

                            {/* Action buttons */}
                            <div className="flex items-center gap-2 ml-4">
                              <button type="button" onClick={() => bm.handleAddBlock(block.id, false)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors flex items-center gap-1" title="Ajouter une action enfant">
                                <Plus className="w-3 h-3" /> Action
                              </button>
                              <button type="button" onClick={() => bm.handleAddBlock(block.id, true)} className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 transition-colors flex items-center gap-1" title="Ajouter un objectif enfant">
                                <Plus className="w-3 h-3" /> Objectif
                              </button>
                              {block.parents.length > 0 && (
                                <button type="button" onClick={() => bm.toggleBlockExpanded(block.id)} className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors">
                                  {bm.expandedBlocks.has(block.id) ? 'Réduire' : 'Conditions'}
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => {
                                  const hasChildren = bm.blocks.some(b => b.parents.includes(block.id));
                                  if (hasChildren) showDeleteBlockedToast();
                                  else bm.handleRemoveBlock(block.id);
                                }}
                                className="p-2 text-red-600 hover:bg-red-50 rounded transition-colors"
                                title="Supprimer le bloc"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        </div>

                        {/* Parent conditions (blue) */}
                        {bm.expandedBlocks.has(block.id) && block.parents.length > 0 && (
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

                        {/* Objective conditions (green) */}
                        {bm.expandedBlocks.has(block.id) && block.isObjectif && (
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
              {errors.blocks && <p className="mt-2 text-sm text-red-500">{errors.blocks}</p>}
            </div>

            {errors.submit && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-600">{errors.submit}</p>
              </div>
            )}

            <div className="flex items-center justify-end gap-4 pt-4 border-t border-gray-200">
              <button type="button" onClick={handleClose} className="px-6 py-3 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors font-medium">
                Annuler
              </button>
              <button type="submit" disabled={createMutation.isPending} className="px-6 py-3 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2">
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
