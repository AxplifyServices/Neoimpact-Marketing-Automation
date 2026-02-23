import { useMemo, useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, GitBranch, Eye, Code2, X } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useQuery } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { metaApi } from '@/lib/api/definitions/meta.api';
import { getApiClient } from '@/lib/api/api-client';
import { getBlockDepth, getBlockDisplayNumber, getHierarchicalNumber, getOrderedBlocks } from '@/lib/block-utils';
import { normalizeBlocks } from '@/lib/modele-normalization';
import type { Block, BlockCondition, CanauxMetadata } from '@/types/modele.types';
import LoadingSpinner from '../../components/LoadingSpinner';
import WorkflowPreview from '../../components/custom/WorkflowPreview';

interface ModeleDetail {
  id_modele: string;
  nom_modele: string;
  date_creation: string;
  liste_action?: string;
  blocks?: unknown;
}

function parseArrayJson(value: string): any[] | null {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function resolveBlocksForView(modele: ModeleDetail | undefined): Block[] {
  if (!modele) return [];

  if (Array.isArray(modele.blocks)) {
    return normalizeBlocks(modele.blocks);
  }

  if (typeof modele.blocks === 'string' && modele.blocks.trim() !== '') {
    const parsedBlocks = parseArrayJson(modele.blocks);
    if (parsedBlocks) return normalizeBlocks(parsedBlocks);
  }

  if (typeof modele.liste_action === 'string' && modele.liste_action.trim() !== '') {
    const parsedLegacy = parseArrayJson(modele.liste_action);
    if (parsedLegacy) return normalizeBlocks(parsedLegacy);
  }

  return [];
}

function formatConditionLabel(condition: BlockCondition, parentCanal?: string, canauxData?: CanauxMetadata): string {
  const op = condition.operator || '=';

  if (condition.type === 'days_since_last') {
    const value = condition.daysSinceLastAction;
    if (value === undefined || value === null) return 'NB jours depuis last action';
    return `NB jours depuis last action ${op} ${value}`;
  }

  if (condition.type === 'flag_resultat') {
    if (!condition.flagResultat) return 'Flag resultats';
    return `Flag resultats = ${condition.flagResultat}`;
  }

  if (condition.type === 'counter') {
    const counterLabel = canauxData?.compteur_by_canal[parentCanal || ''] || 'Compteur';
    const value = condition.counterValue;
    if (value === undefined || value === null) return counterLabel;
    return `${counterLabel} ${op} ${value}`;
  }

  if (condition.type === 'campaign_field') {
    const fieldLabel = condition.campaignField === 'nb_jour_debut_campagne'
      ? 'NB jours depuis debut campagne'
      : (condition.campaignField || 'Champ campagne');
    const value = condition.campaignFieldValue;
    if (value === undefined || value === null) return fieldLabel;
    return `${fieldLabel} ${op} ${value}`;
  }

  if (condition.type === 'client_filter') {
    const fieldLabel = condition.column || 'Client';
    const values = (condition.values || []).filter(Boolean);
    const min = (condition.min ?? '').toString().trim();
    const max = (condition.max ?? '').toString().trim();

    if (values.length > 0) {
      return `${fieldLabel}: ${values.join(', ')}`;
    }
    if (min && max) {
      return `${fieldLabel}: ${min}-${max}`;
    }
    if (min) {
      return `${fieldLabel} >= ${min}`;
    }
    if (max) {
      return `${fieldLabel} <= ${max}`;
    }
    return fieldLabel;
  }

  if (condition.type === 'client_field') {
    const fieldLabel = condition.clientField || 'Client';
    const value = condition.clientFieldValue;
    if (value === undefined || value === null || value === '') return fieldLabel;
    return `${fieldLabel} ${op} ${value}`;
  }

  return condition.type;
}

function ReadOnlyConditions({
  block,
  blocks,
  canauxData,
}: {
  block: Block;
  blocks: Block[];
  canauxData?: CanauxMetadata;
}) {
  return (
    <>
      {block.parents.map((parentId) => {
        const parentBlock = blocks.find((candidate) => candidate.id === parentId);
        const parentLabel = parentBlock?.isObjectif
          ? 'Objectif'
          : (parentBlock?.canal || block.canal);
        const parentCanal = parentBlock?.canal || block.canal;
        const conditions = block.conditionsByParent[parentId] || [];
        if (conditions.length === 0) return null;

        return (
          <div key={parentId} className="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-200">
            <div className="flex items-center gap-2 mb-2">
              <GitBranch className="w-4 h-4 text-blue-600" />
              <span className="text-sm font-medium text-blue-900">
                {conditions.length} condition{conditions.length > 1 ? 's' : ''} (depuis {parentLabel})
              </span>
            </div>
            <div className="space-y-2">
              {conditions.map((condition) => (
                <div key={condition.id} className="bg-white p-2 rounded border border-blue-100 text-sm">
                  <div className="font-medium text-gray-800">
                    {formatConditionLabel(condition, parentCanal, canauxData)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}

function ReadOnlyObjective({
  block,
  canauxData,
}: {
  block: Block;
  canauxData?: CanauxMetadata;
}) {
  return (
    <div className="rounded-lg border border-green-200 bg-green-50 p-4 mt-3">
      <div className="text-sm font-medium text-green-900 mb-2">Bloc objectif</div>
      {block.objectiveConditions.length === 0 ? (
        <div className="text-xs text-green-700/80">Aucune condition objectif</div>
      ) : (
        <div className="space-y-2">
          <div className="text-xs text-green-800">Operateur: {block.objectiveOperator}</div>
          {block.objectiveConditions.map((condition) => (
            <div key={condition.id} className="bg-white p-2 rounded border border-green-100 text-sm">
              <div className="font-medium text-gray-800">
                {formatConditionLabel(condition, block.canal, canauxData)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ViewModelePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const apiClient = getApiClient();

  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [isBlockModalOpen, setIsBlockModalOpen] = useState(false);

  const { data: modele, isLoading: modeleLoading } = useQuery<ModeleDetail>({
    queryKey: ['modele', id],
    queryFn: () => apiClient.request<ModeleDetail>(modelesApi.findById(id!)),
    enabled: !!id,
  });

  const blocks = useMemo(() => resolveBlocksForView(modele), [modele]);
  const orderedBlocks = useMemo(() => getOrderedBlocks(blocks), [blocks]);

  const { data: canauxData, isLoading: canauxLoading } = useQuery<CanauxMetadata>({
    queryKey: ['meta-canaux'],
    queryFn: () => apiClient.request<CanauxMetadata>(metaApi.getCanaux()),
  });

  const isLoading = modeleLoading || canauxLoading;

  const selectedBlock = useMemo(
    () => (activeBlockId ? blocks.find((block) => block.id === activeBlockId) || null : null),
    [activeBlockId, blocks],
  );
  const selectedBlockNumber = selectedBlock ? getHierarchicalNumber(blocks, selectedBlock.id) : '';

  const openBlockModal = useCallback((blockId: string) => {
    setActiveBlockId(blockId);
    setIsBlockModalOpen(true);
  }, []);

  const closeBlockModal = useCallback(() => setIsBlockModalOpen(false), []);

  useEffect(() => {
    if (!isBlockModalOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeBlockModal();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [closeBlockModal, isBlockModalOpen]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      </div>
    );
  }

  if (!modele) {
    return (
      <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
        <div className="max-w-7xl mx-auto">
          <button
            onClick={() => navigate('/modeles')}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
            <span>Retour aux modeles</span>
          </button>
          <div className="text-center py-12">
            <p className="text-gray-500">Modele non trouve</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
      <div className="max-w-7xl mx-auto mb-8">
        <button
          onClick={() => navigate('/modeles')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>Retour aux modeles</span>
        </button>
        <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">{modele.nom_modele}</h1>
        <p className="text-gray-600 mt-2">Mode lecture seule</p>
      </div>

      <div className="max-w-7xl mx-auto">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nom du modele</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {modele.nom_modele}
              </div>
            </div>
          </div>

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
              <div className="text-xs text-gray-500">Lecture seule</div>
            </div>

            <TabsContent value="visual">
              {blocks.length === 0 ? (
                <div className="p-8 border-2 border-dashed border-gray-300 rounded-lg text-center">
                  <GitBranch className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500">Aucune action ajoutee.</p>
                </div>
              ) : (
                <WorkflowPreview
                  blocks={blocks}
                  getBlockDisplayNumber={(blockId) => getBlockDisplayNumber(blocks, blockId)}
                  onSelectBlock={openBlockModal}
                  selectedBlockIds={activeBlockId ? [activeBlockId] : []}
                  showHeader={false}
                  showFrame={false}
                  height="calc(100vh - 280px)"
                  containerClassName="rounded-lg border border-gray-200"
                />
              )}
            </TabsContent>

            <TabsContent value="editor">
              {blocks.length === 0 ? (
                <div className="p-8 border-2 border-dashed border-gray-300 rounded-lg text-center">
                  <GitBranch className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500">Aucune action ajoutee.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {orderedBlocks.map((block) => {
                    const depth = getBlockDepth(blocks, block.id);
                    const hierarchicalNumber = getHierarchicalNumber(blocks, block.id);
                    const isChildBlock = block.parents.length > 0;
                    const totalConditionCount = Object.values(block.conditionsByParent).reduce((sum, conditions) => sum + conditions.length, 0);
                    const conditionLabel = totalConditionCount === 1 ? 'condition' : 'conditions';

                    return (
                      <div key={block.id} className="border border-gray-300 rounded-lg bg-white overflow-hidden" style={{ marginLeft: `${depth * 2}rem` }}>
                        <div className="p-4 bg-gray-50 border-b border-gray-200">
                          <div className="flex items-center gap-3 flex-1">
                            <span className="flex items-center justify-center w-8 h-8 bg-slate-900 text-white rounded-full text-sm font-bold">{hierarchicalNumber}</span>
                            <div className="flex-1">
                              <div className="text-sm font-semibold text-gray-900">{block.isObjectif ? 'Bloc Objectif' : `Canal: ${block.canal}`}</div>
                              <div className="text-xs text-gray-600">
                                <span>Delai: {block.delai}</span>
                                {isChildBlock && <span className="ml-2">- {totalConditionCount} {conditionLabel}</span>}
                              </div>

                              <div className="mt-3 space-y-3">
                                {block.parents.length > 0 && (
                                  <div>
                                    <label className="block text-xs font-medium text-gray-600 mb-1">Parents</label>
                                    <div className="flex flex-wrap gap-1">
                                      {block.parents.map((parentId) => {
                                        const parentBlock = blocks.find((candidate) => candidate.id === parentId);
                                        const parentNum = getBlockDisplayNumber(blocks, parentId);
                                        return (
                                          <span key={parentId} className="inline-flex items-center gap-1 px-2 py-1 bg-gray-200 rounded text-xs">
                                            Bloc {parentNum} - {parentBlock?.isObjectif ? 'Objectif' : (parentBlock?.canal || '?')}
                                          </span>
                                        );
                                      })}
                                    </div>
                                  </div>
                                )}

                                {!block.isObjectif && (
                                  <>
                                    <div>
                                      <label className="block text-xs font-medium text-gray-600 mb-1">Canal</label>
                                      <div className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white">
                                        {block.canal || '-'}
                                      </div>
                                    </div>
                                    {(block.canal === 'Mail' || block.canal === 'EMAIL') && (
                                      <div>
                                        <label className="block text-xs font-medium text-gray-600 mb-1">Objet</label>
                                        <div className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white">
                                          {block.objet || '-'}
                                        </div>
                                      </div>
                                    )}
                                    <div>
                                      <label className="block text-xs font-medium text-gray-600 mb-1">Contenu</label>
                                      <div className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white whitespace-pre-wrap">
                                        {block.contenu || '-'}
                                      </div>
                                    </div>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>

                        {isChildBlock && (
                          <div className="p-4 pt-0">
                            <ReadOnlyConditions block={block} blocks={blocks} canauxData={canauxData} />
                          </div>
                        )}

                        {block.isObjectif && (
                          <div className="p-4 pt-0">
                            <ReadOnlyObjective block={block} canauxData={canauxData} />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {isBlockModalOpen && selectedBlock && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={closeBlockModal}>
          <div className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl bg-white shadow-lg" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-gray-200 p-4">
              <div>
                <div className="text-xs text-gray-500">Bloc {selectedBlockNumber}</div>
                <h3 className="text-lg font-semibold text-gray-900">{selectedBlock.isObjectif ? 'Bloc Objectif' : selectedBlock.canal}</h3>
              </div>
              <button type="button" onClick={closeBlockModal} className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700" aria-label="Close">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4 p-4">
              {selectedBlock.parents.length > 0 && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Parents</label>
                  <div className="flex flex-wrap gap-1">
                    {selectedBlock.parents.map((parentId) => {
                      const parentBlock = blocks.find((candidate) => candidate.id === parentId);
                      const parentNum = getBlockDisplayNumber(blocks, parentId);
                      return (
                        <span key={parentId} className="inline-flex items-center gap-1 rounded bg-gray-200 px-2 py-1 text-xs">
                          Bloc {parentNum} - {parentBlock?.isObjectif ? 'Objectif' : (parentBlock?.canal || '?')}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {!selectedBlock.isObjectif && (
                <>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">Canal</label>
                    <div className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
                      {selectedBlock.canal || '-'}
                    </div>
                  </div>
                  {(selectedBlock.canal === 'Mail' || selectedBlock.canal === 'EMAIL') && (
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">Objet</label>
                      <div className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                        {selectedBlock.objet || '-'}
                      </div>
                    </div>
                  )}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">Contenu</label>
                    <div className="w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm whitespace-pre-wrap">
                      {selectedBlock.contenu || '-'}
                    </div>
                  </div>
                </>
              )}

              <ReadOnlyConditions block={selectedBlock} blocks={blocks} canauxData={canauxData} />

              {selectedBlock.isObjectif && (
                <ReadOnlyObjective block={selectedBlock} canauxData={canauxData} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
