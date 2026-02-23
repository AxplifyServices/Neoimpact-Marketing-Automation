import type { Block, BlockCondition, EditPayload } from '@/types/modele.types';

export function getFieldKind(field: string, numFields: string[]): 'numeric' | 'categorical' {
  return numFields.includes(field) ? 'numeric' : 'categorical';
}

export function formatFieldLabel(field: string): string {
  return field
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function normalizeCanal(canal: string): string {
  return canal.trim().toLowerCase();
}

export function isSpamSensitiveCanal(canal: string): boolean {
  const normalized = normalizeCanal(canal);
  return normalized === 'sms' || normalized === 'mail' || normalized === 'email';
}

export function normalizeParentId(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'string') {
    if (value.startsWith('block_')) return value;
    if (/^\d+$/.test(value)) return `block_${value}`;
    return value;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `block_${value}`;
  }
  return null;
}

function normalizeParentsArray(value: unknown, blocMere?: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(v => normalizeParentId(v)).filter((v): v is string => v !== null);
  }
  const parent = normalizeParentId(blocMere ?? value);
  return parent ? [parent] : [];
}

function parseBackendCondition(oldCond: any, blockId: string | number, idx: number): BlockCondition {
  const condition: BlockCondition = {
    id: `cond_${blockId}_${idx}`,
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
}

function normalizeConditions(conditions: any[], blockId: string): BlockCondition[] {
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
}

function convertOldFormatToNew(parsedBlocks: any[]): Block[] {
  if (!Array.isArray(parsedBlocks) || parsedBlocks.length === 0) return [];

  return parsedBlocks.map((oldBlock: any, blockIndex: number) => {
    const blockId = oldBlock.ID ?? blockIndex;
    const id = `block_${blockId}`;

    const parents = normalizeParentsArray(
      oldBlock.Parents,
      oldBlock['Bloc_mère'] ?? oldBlock['Bloc_mere']
    );

    const conditionsByParent: Record<string, BlockCondition[]> = {};
    if (oldBlock.ConditionsByParent && typeof oldBlock.ConditionsByParent === 'object') {
      for (const [parentId, conds] of Object.entries(oldBlock.ConditionsByParent)) {
        const normalizedPid = normalizeParentId(parentId);
        if (normalizedPid) {
          conditionsByParent[normalizedPid] = (conds as any[] || []).map((c: any, idx: number) =>
            parseBackendCondition(c, blockId, idx)
          );
        }
      }
    } else {
      const flatConds = (oldBlock.Conditions || []).map((c: any, idx: number) =>
        parseBackendCondition(c, blockId, idx)
      );
      if (parents.length > 0 && flatConds.length > 0) {
        conditionsByParent[parents[0]] = flatConds;
      }
      for (const pid of parents) {
        if (!conditionsByParent[pid]) conditionsByParent[pid] = [];
      }
    }

    const objectiveConditions = (oldBlock.ObjectiveConditions || []).map((c: any, idx: number) =>
      parseBackendCondition(c, `${blockId}_obj`, idx)
    );

    return {
      id,
      canal: oldBlock.Canal || '',
      delai: Number(oldBlock.Delai) || 0,
      parents,
      objet: oldBlock.Objet || '',
      contenu: oldBlock.Contenu || '',
      conditionsByParent,
      isObjectif: Boolean(oldBlock.objectif),
      valideObjectif: (oldBlock.valide_objectif === 'Oui' || oldBlock.valide_objectif === 'Non')
        ? oldBlock.valide_objectif as 'Oui' | 'Non'
        : undefined,
      objectiveConditions,
      objectiveOperator: (oldBlock.ObjectiveOperator || 'AND') as 'AND' | 'OR',
    };
  });
}

export function normalizeBlocks(rawBlocks: any[]): Block[] {
  if (!Array.isArray(rawBlocks) || rawBlocks.length === 0) return [];

  const isBackendFormat = rawBlocks.length > 0
    && rawBlocks[0]
    && typeof rawBlocks[0] === 'object'
    && 'ID' in rawBlocks[0];
  if (isBackendFormat) return convertOldFormatToNew(rawBlocks);

  return rawBlocks.map((block: any, index: number) => {
    const idValue = block.id ?? block.ID;
    const id = typeof idValue === 'string'
      ? (idValue.trim() === ''
        ? `block_${Date.now()}_${index}`
        : (/^\d+$/.test(idValue.trim()) ? `block_${idValue.trim()}` : idValue))
      : typeof idValue === 'number'
        ? `block_${idValue}`
        : `block_${Date.now()}_${index}`;

    const parents = Array.isArray(block.parents)
      ? block.parents
      : normalizeParentsArray(block.Parents, block.parentBlockId ?? block['Bloc_mère'] ?? block['Bloc_mere']);

    let conditionsByParent: Record<string, BlockCondition[]> = {};
    if (block.conditionsByParent && typeof block.conditionsByParent === 'object') {
      conditionsByParent = block.conditionsByParent;
    } else {
      const flatConds = normalizeConditions(block.conditions ?? block.Conditions ?? [], id);
      if (parents.length > 0 && flatConds.length > 0) {
        conditionsByParent[parents[0]] = flatConds;
      }
      for (const pid of parents) {
        if (!conditionsByParent[pid]) conditionsByParent[pid] = [];
      }
    }

    const objectiveConditions = Array.isArray(block.objectiveConditions)
      ? block.objectiveConditions
      : (block.ObjectiveConditions || []).map((c: any, idx: number) =>
          parseBackendCondition(c, `${id}_obj`, idx)
        );

    return {
      id,
      canal: block.canal ?? block.Canal ?? '',
      delai: Number(block.delai ?? block.Delai) || 0,
      parents,
      objet: block.objet ?? block.Objet ?? '',
      contenu: block.contenu ?? block.Contenu ?? '',
      conditionsByParent,
      isObjectif: Boolean(block.isObjectif ?? block.objectif),
      valideObjectif: (() => {
        const v = block.valideObjectif ?? block.valide_objectif;
        return v === 'Oui' || v === 'Non' ? v as 'Oui' | 'Non' : undefined;
      })(),
      objectiveConditions,
      objectiveOperator: (block.objectiveOperator ?? block.ObjectiveOperator ?? 'AND') as 'AND' | 'OR',
    };
  });
}

export function resolveBlocksFromPayload(payload: EditPayload): Block[] {
  if (Array.isArray(payload.blocks) && payload.blocks.length > 0) {
    return normalizeBlocks(payload.blocks);
  }
  if (typeof payload.blocks === 'string') {
    try {
      return normalizeBlocks(JSON.parse(payload.blocks));
    } catch {
      return [];
    }
  }
  if (payload.liste_action) {
    try {
      return normalizeBlocks(JSON.parse(payload.liste_action));
    } catch {
      return [];
    }
  }
  return [];
}
