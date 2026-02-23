import { useState, type SetStateAction } from 'react';
import type { Block, BlockCondition, ConditionType, CanauxMetadata } from '@/types/modele.types';

interface SetBlocksOptions {
  recordHistory?: boolean;
  resetHistory?: boolean;
}

const areSameBlockRefs = (left: Block[], right: Block[]): boolean => {
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
};

export function useBlockManagement(canauxData?: CanauxMetadata) {
  const [blocks, setBlocksState] = useState<Block[]>([]);
  const [history, setHistory] = useState<Block[][]>([]);
  const [future, setFuture] = useState<Block[][]>([]);
  const [expandedBlocks, setExpandedBlocks] = useState<Set<string>>(new Set());

  const setBlocks = (updater: SetStateAction<Block[]>, options?: SetBlocksOptions) => {
    const recordHistory = options?.recordHistory ?? true;
    const resetHistory = options?.resetHistory ?? false;

    setBlocksState((prev) => {
      const next = typeof updater === 'function'
        ? (updater as (previousState: Block[]) => Block[])(prev)
        : updater;

      if (next === prev || areSameBlockRefs(next, prev)) return prev;

      if (resetHistory) {
        setHistory([]);
        setFuture([]);
      } else if (recordHistory) {
        setHistory((prevHistory) => {
          const nextHistory = [...prevHistory, prev];
          return nextHistory.length > 100 ? nextHistory.slice(nextHistory.length - 100) : nextHistory;
        });
        setFuture([]);
      }

      return next;
    });
  };

  const undo = () => {
    setHistory((prevHistory) => {
      if (prevHistory.length === 0) return prevHistory;
      const previousBlocks = prevHistory[prevHistory.length - 1];

      setBlocksState((currentBlocks) => {
        setFuture((prevFuture) => [currentBlocks, ...prevFuture].slice(0, 100));
        return previousBlocks;
      });

      return prevHistory.slice(0, -1);
    });
  };

  const redo = () => {
    setFuture((prevFuture) => {
      if (prevFuture.length === 0) return prevFuture;
      const nextBlocks = prevFuture[0];

      setBlocksState((currentBlocks) => {
        setHistory((prevHistory) => [...prevHistory, currentBlocks].slice(-100));
        return nextBlocks;
      });

      return prevFuture.slice(1);
    });
  };

  const createCondition = (type: ConditionType, block: Block): BlockCondition => {
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
      newCondition.column = '';
      newCondition.min = '';
      newCondition.max = '';
      newCondition.values = [];
    } else if (type === 'campaign_field') {
      newCondition.campaignField = 'nb_jour_debut_campagne';
      newCondition.campaignFieldValue = 0;
      newCondition.operator = '>=';
    }

    return newCondition;
  };

  const handleAddBlock = (parentId: string | null = null, isObjectif: boolean = false): string => {
    const defaultCanal = canauxData?.canaux[0] || 'Appel';
    const parents = parentId ? [parentId] : [];
    const conditionsByParent: Record<string, BlockCondition[]> = {};
    if (parentId) conditionsByParent[parentId] = [];

    const parentIsObjectif = parentId ? (blocks.find(b => b.id === parentId)?.isObjectif ?? false) : false;

    const newBlock: Block = {
      id: `block_${Date.now()}`,
      canal: isObjectif ? '' : defaultCanal,
      delai: 0,
      parents,
      conditionsByParent,
      isObjectif,
      valideObjectif: parentIsObjectif ? 'Non' : undefined,
      objectiveConditions: [],
      objectiveOperator: 'AND',
    };

    setBlocks((prev) => [...prev, newBlock]);
    setExpandedBlocks(prev => {
      if (parentId !== null) {
        return new Set([newBlock.id]);
      }
      const next = new Set(prev);
      next.add(newBlock.id);
      return next;
    });

    return newBlock.id;
  };

  const handleRemoveBlock = (blockId: string) => {
    setBlocks((prev) => {
      const updatedBlocks = prev.filter(b => b.id !== blockId);
      return updatedBlocks.map(block => {
        const newParents = block.parents.filter(pid => pid !== blockId);
        const newCondsByParent = { ...block.conditionsByParent };
        delete newCondsByParent[blockId];

        const cleanedCondsByParent: Record<string, BlockCondition[]> = {};
        for (const [pid, conds] of Object.entries(newCondsByParent)) {
          cleanedCondsByParent[pid] = conds.map(cond => ({
            ...cond,
            nextBlockId: cond.nextBlockId === blockId ? null : cond.nextBlockId,
          }));
        }

        return { ...block, parents: newParents, conditionsByParent: cleanedCondsByParent };
      });
    });
    setExpandedBlocks(prev => {
      const next = new Set(prev);
      next.delete(blockId);
      return next;
    });
  };

  const handleBlockChange = (blockId: string, field: keyof Block, value: any) => {
    setBlocks((prev) => prev.map(block =>
      block.id === blockId ? { ...block, [field]: value } : block
    ));
  };

  const handleAddParent = (blockId: string, parentId: string) => {
    setBlocks((prev) => prev.map(block => {
      if (block.id !== blockId) return block;
      if (block.parents.includes(parentId)) return block;
      return {
        ...block,
        parents: [...block.parents, parentId],
        conditionsByParent: { ...block.conditionsByParent, [parentId]: [] },
      };
    }));
  };

  const handleRemoveParent = (blockId: string, parentId: string) => {
    setBlocks((prev) => prev.map(block => {
      if (block.id !== blockId) return block;
      const newParents = block.parents.filter(p => p !== parentId);
      const updatedConditions = { ...block.conditionsByParent };
      delete updatedConditions[parentId];
      return { ...block, parents: newParents, conditionsByParent: updatedConditions };
    }));
  };

  const handleAddCondition = (blockId: string, parentId: string, type: ConditionType) => {
    setBlocks((prev) => prev.map(block => {
      if (block.id !== blockId) return block;
      const newCondition = createCondition(type, block);
      const updatedConditions = { ...block.conditionsByParent };
      updatedConditions[parentId] = [...(updatedConditions[parentId] || []), newCondition];
      return { ...block, conditionsByParent: updatedConditions };
    }));
  };

  const handleRemoveCondition = (blockId: string, parentId: string, conditionId: string) => {
    setBlocks((prev) => prev.map(block => {
      if (block.id !== blockId) return block;
      const updatedConditions = { ...block.conditionsByParent };
      updatedConditions[parentId] = (updatedConditions[parentId] || []).filter(c => c.id !== conditionId);
      return { ...block, conditionsByParent: updatedConditions };
    }));
  };

  const handleConditionChange = (blockId: string, parentId: string, conditionId: string, field: string, value: any) => {
    setBlocks((prev) => prev.map(block => {
      if (block.id !== blockId) return block;
      const updatedConditions = { ...block.conditionsByParent };
      updatedConditions[parentId] = (updatedConditions[parentId] || []).map(cond =>
        cond.id === conditionId ? { ...cond, [field]: value } : cond
      );
      return { ...block, conditionsByParent: updatedConditions };
    }));
  };

  const handleAddObjectiveCondition = (blockId: string, type: ConditionType = 'client_filter') => {
    setBlocks((prev) => prev.map(block => {
      if (block.id !== blockId) return block;
      const newCondition = createCondition(type, block);
      return { ...block, objectiveConditions: [...block.objectiveConditions, newCondition] };
    }));
  };

  const handleRemoveObjectiveCondition = (blockId: string, conditionId: string) => {
    setBlocks((prev) => prev.map(block => {
      if (block.id !== blockId) return block;
      return { ...block, objectiveConditions: block.objectiveConditions.filter(c => c.id !== conditionId) };
    }));
  };

  const handleObjectiveConditionChange = (blockId: string, conditionId: string, field: string, value: any) => {
    setBlocks((prev) => prev.map(block => {
      if (block.id !== blockId) return block;
      return {
        ...block,
        objectiveConditions: block.objectiveConditions.map(c =>
          c.id === conditionId ? { ...c, [field]: value } : c
        ),
      };
    }));
  };

  const toggleBlockExpanded = (blockId: string) => {
    setExpandedBlocks(prev => {
      const next = new Set(prev);
      if (next.has(blockId)) {
        next.delete(blockId);
      } else {
        next.add(blockId);
      }
      return next;
    });
  };

  return {
    blocks,
    setBlocks,
    canUndo: history.length > 0,
    canRedo: future.length > 0,
    undo,
    redo,
    expandedBlocks,
    setExpandedBlocks,
    handleAddBlock,
    handleRemoveBlock,
    handleBlockChange,
    handleAddParent,
    handleRemoveParent,
    handleAddCondition,
    handleRemoveCondition,
    handleConditionChange,
    handleAddObjectiveCondition,
    handleRemoveObjectiveCondition,
    handleObjectiveConditionChange,
    toggleBlockExpanded,
    createCondition,
  };
}
