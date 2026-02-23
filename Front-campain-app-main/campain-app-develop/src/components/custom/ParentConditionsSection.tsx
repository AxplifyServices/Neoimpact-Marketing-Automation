import { GitBranch } from 'lucide-react';
import type { Block, CanauxMetadata, CampaignConditionField } from '@/types/modele.types';
import { getBlockDisplayNumber } from '@/lib/block-utils';
import ConditionRenderer from './ConditionRenderer';

interface ParentConditionsSectionProps {
  block: Block;
  blocks: Block[];
  canauxData?: CanauxMetadata;
  campaignConditionFields?: { fields: CampaignConditionField[] };
  allFields: string[];
  numFields: string[];
  valuesByField: Record<string, string[]>;
  onAddCondition: (blockId: string, parentId: string, type: string) => void;
  onRemoveCondition: (blockId: string, parentId: string, conditionId: string) => void;
  onConditionChange: (blockId: string, parentId: string, conditionId: string, field: string, value: any) => void;
  formatFieldLabel: (col: string) => string;
  getFieldKind: (col: string) => 'numeric' | 'categorical';
}

export default function ParentConditionsSection({
  block,
  blocks,
  canauxData,
  campaignConditionFields,
  allFields,
  numFields,
  valuesByField,
  onAddCondition,
  onRemoveCondition,
  onConditionChange,
  formatFieldLabel,
  getFieldKind,
}: ParentConditionsSectionProps) {
  if (block.parents.length === 0) return null;

  return (
    <div className="p-4 bg-blue-50 space-y-4">
      {block.parents.map(pid => {
        const parentBlock = blocks.find(b => b.id === pid);
        const parentNum = getBlockDisplayNumber(blocks, pid);
        const parentCanal = parentBlock?.canal || block.canal;
        const parentConds = block.conditionsByParent[pid] || [];

        return (
          <div key={pid} className="border border-blue-200 rounded-lg p-3 bg-white">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-blue-600" />
                <span className="text-xs font-semibold text-blue-800">
                  Conditions depuis Bloc {parentNum} ({parentCanal})
                </span>
              </div>
              <div className="flex gap-1 flex-wrap">
                <button type="button" onClick={() => onAddCondition(block.id, pid, 'days_since_last')} className="px-2 py-0.5 text-xs bg-blue-50 border border-blue-200 rounded hover:bg-blue-100">+ Jours</button>
                <button type="button" onClick={() => onAddCondition(block.id, pid, 'flag_resultat')} className="px-2 py-0.5 text-xs bg-blue-50 border border-blue-200 rounded hover:bg-blue-100">+ Flag</button>
                <button type="button" onClick={() => onAddCondition(block.id, pid, 'counter')} className="px-2 py-0.5 text-xs bg-blue-50 border border-blue-200 rounded hover:bg-blue-100">+ {canauxData?.compteur_by_canal[parentCanal] || 'Compteur'}</button>
                <button type="button" onClick={() => onAddCondition(block.id, pid, 'client_filter')} className="px-2 py-0.5 text-xs bg-blue-50 border border-blue-200 rounded hover:bg-blue-100">+ Client</button>
                <button type="button" onClick={() => onAddCondition(block.id, pid, 'campaign_field')} className="px-2 py-0.5 text-xs bg-purple-50 border border-purple-200 rounded hover:bg-purple-100">+ Campagne</button>
              </div>
            </div>
            {parentConds.length === 0 ? (
              <div className="text-center py-2 text-gray-400 text-xs">Aucune condition</div>
            ) : (
              <div className="space-y-2">
                {parentConds.map(condition => (
                  <ConditionRenderer
                    key={condition.id}
                    condition={condition}
                    blockId={block.id}
                    parentId={pid}
                    parentCanal={parentCanal}
                    canauxData={canauxData}
                    campaignConditionFields={campaignConditionFields}
                    allFields={allFields}
                    numFields={numFields}
                    valuesByField={valuesByField}
                    onConditionChange={onConditionChange}
                    onRemoveCondition={onRemoveCondition}
                    formatFieldLabel={formatFieldLabel}
                    getFieldKind={getFieldKind}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
