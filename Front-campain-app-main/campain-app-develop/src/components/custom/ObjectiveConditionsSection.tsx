import { Trash2 } from 'lucide-react';
import type { Block } from '@/types/modele.types';

interface ObjectiveConditionsSectionProps {
  block: Block;
  allFields: string[];
  numFields: string[];
  valuesByField: Record<string, string[]>;
  onBlockChange: (blockId: string, field: keyof Block, value: any) => void;
  onAddObjectiveCondition: (blockId: string) => void;
  onRemoveObjectiveCondition: (blockId: string, conditionId: string) => void;
  onObjectiveConditionChange: (blockId: string, conditionId: string, field: string, value: any) => void;
  formatFieldLabel: (col: string) => string;
  getFieldKind: (col: string) => 'numeric' | 'categorical';
}

export default function ObjectiveConditionsSection({
  block,
  allFields,
  numFields,
  valuesByField,
  onBlockChange,
  onAddObjectiveCondition,
  onRemoveObjectiveCondition,
  onObjectiveConditionChange,
  formatFieldLabel,
  getFieldKind,
}: ObjectiveConditionsSectionProps) {
  if (!block.isObjectif) return null;

  return (
    <div className="p-4 bg-green-50 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-green-800">Conditions Objectif</span>
        <div className="flex items-center gap-2">
          <select
            value={block.objectiveOperator}
            onChange={(e) => onBlockChange(block.id, 'objectiveOperator', e.target.value)}
            className="rounded border border-green-300 px-2 py-1 text-xs"
          >
            <option value="AND">ET (AND)</option>
            <option value="OR">OU (OR)</option>
          </select>
          <button
            type="button"
            onClick={() => onAddObjectiveCondition(block.id)}
            className="px-2 py-0.5 text-xs bg-green-100 border border-green-300 rounded hover:bg-green-200"
          >
            + Condition objectif
          </button>
        </div>
      </div>

      {block.objectiveConditions.length === 0 ? (
        <div className="text-center py-2 text-gray-400 text-xs">Aucune condition objectif</div>
      ) : (
        <div className="space-y-2">
          {block.objectiveConditions.map(cond => (
            <div key={cond.id} className="flex items-center gap-2 rounded bg-white p-3 border border-green-200">
              <div className="flex-1 space-y-2">
                <select
                  value={cond.column || ''}
                  onChange={(e) => onObjectiveConditionChange(block.id, cond.id, 'column', e.target.value)}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                >
                  <option value="">Colonne...</option>
                  {allFields.map(col => <option key={col} value={col}>{formatFieldLabel(col)}</option>)}
                </select>
                {cond.column && getFieldKind(cond.column) === 'numeric' ? (
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="number"
                      value={cond.min ?? ''}
                      onChange={(e) => onObjectiveConditionChange(block.id, cond.id, 'min', e.target.value)}
                      placeholder="Min"
                      className="rounded border border-gray-300 px-2 py-1 text-sm"
                    />
                    <input
                      type="number"
                      value={cond.max ?? ''}
                      onChange={(e) => onObjectiveConditionChange(block.id, cond.id, 'max', e.target.value)}
                      placeholder="Max"
                      className="rounded border border-gray-300 px-2 py-1 text-sm"
                    />
                  </div>
                ) : cond.column && valuesByField[cond.column] ? (
                  <select
                    value={cond.values?.[0] || ''}
                    onChange={(e) => onObjectiveConditionChange(block.id, cond.id, 'values', [e.target.value])}
                    className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                  >
                    <option value="">Valeur...</option>
                    {valuesByField[cond.column].map(v => <option key={v} value={v}>{v}</option>)}
                  </select>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => onRemoveObjectiveCondition(block.id, cond.id)}
                className="rounded p-1 text-red-600 hover:bg-red-50"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
