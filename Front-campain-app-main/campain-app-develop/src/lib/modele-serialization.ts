import type { Block, BlockCondition, CanauxMetadata } from '@/types/modele.types';
import { getOrderedBlocks } from '@/lib/block-utils';

export function serializeCondition(
  cond: BlockCondition,
  canauxData?: CanauxMetadata,
  parentCanal?: string,
): Record<string, any> {
  const condition: Record<string, any> = {};

  if (cond.type === 'flag_resultat' && cond.flagResultat) {
    condition.field = 'Flag résultats';
    condition.op = cond.operator || '=';
    condition.value = cond.flagResultat;
  } else if (cond.type === 'days_since_last' && cond.daysSinceLastAction !== undefined) {
    condition.field = 'NB jours depuis last action';
    condition.op = cond.operator || '=';
    condition.value = cond.daysSinceLastAction;
  } else if (cond.type === 'counter' && cond.counterValue !== undefined) {
    const compteur = canauxData?.compteur_by_canal[parentCanal || ''] || 'NB_appel';
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
  } else if (cond.type === 'client_filter' && cond.column) {
    const values = (cond.values || []).filter(Boolean);
    const min = (cond.min || '').toString().trim();
    const max = (cond.max || '').toString().trim();

    condition.field = `client.${cond.column}`;
    if (values.length > 0) {
      condition.op = '=';
      condition.value = values[0];
    } else if (min) {
      condition.op = '>=';
      condition.value = min;
    } else if (max) {
      condition.op = '<=';
      condition.value = max;
    }
  }

  return condition;
}

export function buildBlocksPayload(
  blocks: Block[],
  canauxData?: CanauxMetadata,
): { orderedBlocks: Block[]; blockIdMapping: Map<string, number>; serializedBlocks: Record<string, any>[] } {
  const orderedBlocks = getOrderedBlocks(blocks);
  const blockIdMapping = new Map<string, number>();
  orderedBlocks.forEach((block, index) => {
    blockIdMapping.set(block.id, index + 1);
  });

  const objectiveParentIds = new Set(
    blocks.filter(block => block.isObjectif).map(block => block.id),
  );

  const serializedBlocks = orderedBlocks.map(block => {
    const blockNumId = blockIdMapping.get(block.id);

    const Parents = block.parents
      .map(pid => String(blockIdMapping.get(pid)))
      .filter(pid => pid !== 'undefined');

    const hasObjectiveParent = block.parents.some(pid => objectiveParentIds.has(pid));
    const valideObjectif = hasObjectiveParent
      ? (block.valideObjectif ?? 'Non')
      : 'no_goal';

    const ConditionsByParent: Record<string, any[]> = {};
    for (const pid of block.parents) {
      const mappedPid = String(blockIdMapping.get(pid));
      const parentBlock = blocks.find(b => b.id === pid);
      const parentCanal = parentBlock?.canal || block.canal;
      const conds = (block.conditionsByParent[pid] || [])
        .map(c => serializeCondition(c, canauxData, parentCanal))
        .filter(c => Object.keys(c).length > 0);
      ConditionsByParent[mappedPid] = conds;
    }

    const ObjectiveConditions = block.objectiveConditions
      .map(c => serializeCondition(c, canauxData))
      .filter(c => Object.keys(c).length > 0);

    const blockPayload: Record<string, any> = {
      ID: blockNumId,
      Parents,
      ConditionsByParent,
      Conditions: [],
      objectif: block.isObjectif,
      valide_objectif: valideObjectif,
    };

    if (block.isObjectif) {
      blockPayload.ObjectiveConditions = ObjectiveConditions;
      blockPayload.ObjectiveOperator = block.objectiveOperator;
    } else {
      blockPayload.Canal = block.canal;
      blockPayload.Action = canauxData?.actions_by_canal[block.canal] || block.canal;
      blockPayload.Objet = block.canal === 'Mail' || block.canal === 'EMAIL' ? (block.objet || '') : '';
      blockPayload.Contenu = block.contenu || '';
    }

    return blockPayload;
  });

  return { orderedBlocks, blockIdMapping, serializedBlocks };
}
