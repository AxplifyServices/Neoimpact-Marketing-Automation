import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, GitBranch } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { modelesApi } from '@/lib/api/definitions/modeles.api';
import { metaApi } from '@/lib/api/definitions/meta.api';
import { getApiClient } from '@/lib/api/api-client';
import LoadingSpinner from '../../components/LoadingSpinner';
import WorkflowPreview from '../../components/custom/WorkflowPreview';
import { parseObjectif, formatObjectifSummary } from '@/lib/utils';

interface Block {
  id: string;
  canal: string;
  delai: number;
  parentBlockId: string | null;
  objet?: string;
  contenu?: string;
  conditions: BlockCondition[];
}

type ConditionType = 'days_since_last' | 'flag_resultat' | 'counter' | 'campaign_field' | 'client_field';

interface BlockCondition {
  id: string;
  type: ConditionType;
  operator?: string;
  daysSinceLastAction?: number;
  flagResultat?: string;
  counterValue?: number;
  campaignField?: string;
  campaignFieldValue?: number;
  clientField?: string;
  clientFieldValue?: string;
  nextBlockId: string | null;
}

interface CanauxMetadata {
  canaux: string[];
  actions_by_canal: Record<string, string>;
  resultats_by_canal: Record<string, string[]>;
  compteur_by_canal: Record<string, string>;
}

interface ModeleDetail {
  id_modele: string;
  nom_modele: string;
  variable_cible: string;
  objectif: string;
  date_creation: string;
  liste_action?: string;
  blocks?: Block[];
}

export default function ViewModelePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const apiClient = getApiClient();

  // Fetch modele details
  const { data: modeleRaw, isLoading: modeleLoading } = useQuery<ModeleDetail>({
    queryKey: ['modele', id],
    queryFn: () => apiClient.request<ModeleDetail>(modelesApi.findById(id!)),
    enabled: !!id,
  });

  // Parse liste_action JSON string into blocks array and convert old format to new
  const modele = modeleRaw ? {
    ...modeleRaw,
    blocks: modeleRaw.liste_action ? convertOldFormatToNew(JSON.parse(modeleRaw.liste_action)) : []
  } : undefined;

  // Convert old format blocks (with uppercase fields) to new format
  function convertOldFormatToNew(parsedBlocks: any[]): Block[] {
    if (!Array.isArray(parsedBlocks) || parsedBlocks.length === 0) return [];

    // Check if it's old format (has uppercase ID field)
    const isOldFormat = 'ID' in parsedBlocks[0];

    if (!isOldFormat) {
      // Already in new format, just return
      return parsedBlocks as Block[];
    }

    // Convert old format to new
    return parsedBlocks.map((oldBlock: any) => ({
      id: `block_${oldBlock.ID}`,
      canal: oldBlock.Canal || '',
      delai: 0,
      parentBlockId: oldBlock.Bloc_mère ? `block_${oldBlock.Bloc_mère}` : null,
      objet: oldBlock.Objet || '',
      contenu: oldBlock.Contenu || '',
      conditions: (oldBlock.Conditions || []).map((oldCond: any, idx: number) => {
        const condition: BlockCondition = {
          id: `cond_${Date.now()}_${idx}`,
          type: 'flag_resultat', // Default type
          nextBlockId: null,
        };

        // Map old condition format to new
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
        } else if (oldCond.field === 'nb_jour_debut_campagne') {
          condition.type = 'campaign_field';
          condition.campaignField = oldCond.field;
          condition.campaignFieldValue = oldCond.value;
          condition.operator = oldCond.op || '>=';
        } else if (oldCond.field?.startsWith('client.')) {
          condition.type = 'client_field';
          condition.clientField = oldCond.field.replace('client.', '');
          condition.clientFieldValue = oldCond.value;
          condition.operator = oldCond.op || '=';
        }

        // Map next block
        if (oldCond.next_block_id) {
          condition.nextBlockId = `block_${oldCond.next_block_id}`;
        }

        return condition;
      }),
    }));
  }

  // Fetch canaux metadata
  const { data: canauxData, isLoading: canauxLoading } = useQuery<CanauxMetadata>({
    queryKey: ['meta-canaux'],
    queryFn: () => apiClient.request<CanauxMetadata>(metaApi.getCanaux()),
  });

  // Helper functions
  const getBlockDepth = (blockId: string, blocks: Block[]): number => {
    const block = blocks.find(b => b.id === blockId);
    if (!block || !block.parentBlockId) return 0;
    return 1 + getBlockDepth(block.parentBlockId, blocks);
  };

  const getOrderedBlocks = (blocks: Block[]): Block[] => {
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

  const getBlockDisplayNumber = (blockId: string, blocks: Block[]): number => {
    const orderedBlocks = getOrderedBlocks(blocks);
    return orderedBlocks.findIndex(b => b.id === blockId) + 1;
  };

  const isLoading = modeleLoading || canauxLoading;

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
            <span>Retour aux modèles</span>
          </button>
          <div className="text-center py-12">
            <p className="text-gray-500">Modèle non trouvé</p>
          </div>
        </div>
      </div>
    );
  }

  const blocks = modele.blocks || [];
  const orderedBlocks = getOrderedBlocks(blocks);

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <button
          onClick={() => navigate('/modeles')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>Retour aux modèles</span>
        </button>

        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">{modele.nom_modele}</h1>
            <p className="text-gray-600 mt-2">Détails du modèle de campagne (lecture seule)</p>
          </div>
          <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-medium">
            Lecture seule
          </span>
        </div>
      </div>

      <div className="max-w-7xl mx-auto">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-6">
          {/* Basic Information */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nom du modèle</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {modele.nom_modele}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Variable cible</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {modele.variable_cible}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Objectif</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {(() => {
                  const parsed = parseObjectif(modele.objectif);
                  if (parsed.kind === 'empty') {
                    return <span className="text-gray-400">Non défini</span>;
                  }
                  if (parsed.kind === 'multi') {
                    const opLabel = parsed.op === 'AND' ? 'ET' : 'OU';
                    const opColor = parsed.op === 'AND' ? 'bg-violet-500' : 'bg-amber-500';
                    return (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {parsed.items.map((item, idx) => (
                          <span key={idx} className="flex items-center gap-1.5">
                            {idx > 0 && (
                              <span className={`${opColor} text-white text-[10px] font-bold px-1.5 py-0.5 rounded`}>
                                {opLabel}
                              </span>
                            )}
                            <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                              item.type === 'num' ? 'bg-sky-100 text-sky-700' : 'bg-blue-100 text-blue-700'
                            }`}>
                              {item.variable}: {item.label}
                            </span>
                          </span>
                        ))}
                      </div>
                    );
                  }
                  return formatObjectifSummary(parsed);
                })()}
              </div>
            </div>
          </div>

          {/* Workflow Section */}
          <div className="border-t pt-6">
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700">Workflow</label>
              <p className="text-xs text-gray-500 mt-1">
                Structure du workflow avec {blocks.length} action{blocks.length > 1 ? 's' : ''}
              </p>
            </div>

            {blocks.length === 0 ? (
              <div className="p-8 border-2 border-dashed border-gray-300 rounded-lg text-center">
                <GitBranch className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                <p className="text-gray-500">Aucune action dans ce modèle.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {orderedBlocks.map((block) => {
                  const depth = getBlockDepth(block.id, blocks);
                  const blockNumber = getBlockDisplayNumber(block.id, blocks);

                  return (
                    <div
                      key={block.id}
                      className="border border-gray-300 rounded-lg bg-gray-50 overflow-hidden"
                      style={{ marginLeft: `${depth * 2}rem` }}
                    >
                      <div className="p-4">
                        <div className="flex items-center gap-3 mb-3">
                          <span className="flex items-center justify-center w-8 h-8 bg-slate-900 text-white rounded-full text-sm font-bold">
                            {blockNumber}
                          </span>
                          <div className="flex-1">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Canal</label>
                                <div className="px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm">
                                  {block.canal}
                                </div>
                              </div>

                              {block.canal === 'EMAIL' && block.objet && (
                                <div>
                                  <label className="block text-xs font-medium text-gray-600 mb-1">Objet</label>
                                  <div className="px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm">
                                    {block.objet}
                                  </div>
                                </div>
                              )}
                            </div>

                            {block.contenu && (
                              <div className="mt-3">
                                <label className="block text-xs font-medium text-gray-600 mb-1">Contenu</label>
                                <div className="px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm whitespace-pre-wrap">
                                  {block.contenu}
                                </div>
                              </div>
                            )}

                            {block.conditions.length > 0 && (
                              <div className="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-200">
                                <div className="flex items-center gap-2 mb-2">
                                  <GitBranch className="w-4 h-4 text-blue-600" />
                                  <span className="text-sm font-medium text-blue-900">
                                    {block.conditions.length} condition{block.conditions.length > 1 ? 's' : ''}
                                  </span>
                                </div>
                                <div className="space-y-2">
                                  {block.conditions.map((condition) => {
                                    let conditionText = '';
                                    if (condition.type === 'days_since_last') {
                                      conditionText = `NB jours depuis last action ${condition.operator} ${condition.daysSinceLastAction}`;
                                    } else if (condition.type === 'flag_resultat') {
                                      conditionText = `Flag résultats = ${condition.flagResultat}`;
                                    } else if (condition.type === 'counter') {
                                      const parentBlock = blocks.find(b => b.id === block.parentBlockId);
                                      const parentCanal = parentBlock?.canal || block.canal;
                                      const counterLabel = canauxData?.compteur_by_canal[parentCanal] || 'NB_appel';
                                      conditionText = `${counterLabel} ${condition.operator} ${condition.counterValue}`;
                                    } else if (condition.type === 'campaign_field') {
                                      conditionText = `NB jours depuis début campagne ${condition.operator} ${condition.campaignFieldValue}`;
                                    } else if (condition.type === 'client_field') {
                                      conditionText = `${condition.clientField} ${condition.operator} ${condition.clientFieldValue}`;
                                    }

                                    const nextBlockText = condition.nextBlockId
                                      ? `Bloc ${getBlockDisplayNumber(condition.nextBlockId, blocks)}`
                                      : 'Fin du workflow';

                                    return (
                                      <div key={condition.id} className="bg-white p-2 rounded border border-blue-100 text-sm">
                                        <div className="font-medium text-gray-800">{conditionText}</div>
                                        <div className="text-xs text-gray-600 mt-1">→ Alors aller à: {nextBlockText}</div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Workflow Preview */}
          {blocks.length > 0 && (
            <WorkflowPreview blocks={blocks} getBlockDisplayNumber={(id) => getBlockDisplayNumber(id, blocks)} />
          )}
        </div>
      </div>
    </div>
  );
}
