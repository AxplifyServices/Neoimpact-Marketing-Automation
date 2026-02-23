import { Trash2 } from 'lucide-react';
import type { BlockCondition, CanauxMetadata, CampaignConditionField } from '@/types/modele.types';

interface ConditionRendererProps {
  condition: BlockCondition;
  blockId: string;
  parentId: string;
  parentCanal: string;
  canauxData?: CanauxMetadata;
  campaignConditionFields?: { fields: CampaignConditionField[] };
  allFields: string[];
  numFields: string[];
  valuesByField: Record<string, string[]>;
  onConditionChange: (blockId: string, parentId: string, conditionId: string, field: string, value: any) => void;
  onRemoveCondition: (blockId: string, parentId: string, conditionId: string) => void;
  formatFieldLabel: (col: string) => string;
  getFieldKind: (col: string) => 'numeric' | 'categorical';
}

const OPERATORS = [
  { value: '=', label: '=' },
  { value: '>', label: '>' },
  { value: '<', label: '<' },
  { value: '<=', label: '<=' },
  { value: '>=', label: '>=' },
];

const OPERATORS_WITH_NEQ = [
  ...OPERATORS,
  { value: '!=', label: '!=' },
];

export default function ConditionRenderer({
  condition,
  blockId,
  parentId,
  parentCanal,
  canauxData,
  campaignConditionFields,
  allFields,
  numFields,
  valuesByField,
  onConditionChange,
  onRemoveCondition,
  formatFieldLabel,
  getFieldKind,
}: ConditionRendererProps) {
  const onChange = (field: string, value: any) => onConditionChange(blockId, parentId, condition.id, field, value);

  return (
    <div className="rounded-lg border border-blue-200 bg-white p-3">
      <div className="flex items-start gap-3">
        <div className="flex-1">
          {condition.type === 'days_since_last' && (
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">NB jours depuis last action</label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Operateur</label>
                  <select value={condition.operator || '='} onChange={(e) => onChange('operator', e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Valeur</label>
                  <input type="number" value={condition.daysSinceLastAction || 1} onChange={(e) => onChange('daysSinceLastAction', parseInt(e.target.value) || 1)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" min="1" />
                </div>
              </div>
            </div>
          )}

          {condition.type === 'flag_resultat' && (
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">Flag resultats</label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Operateur</label>
                  <select value="=" disabled className="w-full rounded-lg border border-gray-300 bg-gray-100 px-3 py-2 text-sm"><option value="=">=</option></select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Valeur</label>
                  <select value={condition.flagResultat || ''} onChange={(e) => onChange('flagResultat', e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    <option value="">Selectionner...</option>
                    {(canauxData?.resultats_by_canal[parentCanal] || []).map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}

          {condition.type === 'counter' && (
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">{canauxData?.compteur_by_canal[parentCanal] || 'NB_appel'}</label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Operateur</label>
                  <select value={condition.operator || '='} onChange={(e) => onChange('operator', e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Valeur</label>
                  <input type="number" value={condition.counterValue || 1} onChange={(e) => onChange('counterValue', parseInt(e.target.value) || 1)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" min="1" />
                </div>
              </div>
            </div>
          )}

          {condition.type === 'client_filter' && (
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">Filtre client</label>
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Colonne</label>
                  <select value={condition.column || ''} onChange={(e) => onChange('column', e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    <option value="">Selectionner...</option>
                    {allFields.map((col) => <option key={col} value={col}>{formatFieldLabel(col)}</option>)}
                  </select>
                </div>
                {condition.column && (
                  <div className="text-xs text-gray-500">Type: <span className="font-semibold text-gray-700">{getFieldKind(condition.column)}</span></div>
                )}
                {condition.column && getFieldKind(condition.column) === 'numeric' ? (
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">Min</label>
                      <input type="number" value={condition.min ?? ''} onChange={(e) => onChange('min', e.target.value)} placeholder="Min" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">Max</label>
                      <input type="number" value={condition.max ?? ''} onChange={(e) => onChange('max', e.target.value)} placeholder="Max" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                    </div>
                  </div>
                ) : condition.column && valuesByField[condition.column] ? (
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">Valeur</label>
                    <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-gray-200 p-3">
                      {valuesByField[condition.column].map((m) => (
                        <label key={m} className="flex cursor-pointer items-center gap-2">
                          <input type="radio" name={`filter-${condition.id}`} checked={condition.values?.[0] === m} onChange={() => onChange('values', [m])} className="h-4 w-4 border-gray-300 text-pink-600 focus:ring-pink-500" />
                          <span className="text-sm text-gray-700">{m}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          )}

          {condition.type === 'campaign_field' && (
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">
                {campaignConditionFields?.fields?.find(f => f.db_field === condition.campaignField)?.field || 'NB jours depuis debut campagne'}
              </label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Operateur</label>
                  <select value={condition.operator || '='} onChange={(e) => onChange('operator', e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Valeur (jours)</label>
                  <input type="number" value={condition.campaignFieldValue ?? 0} onChange={(e) => onChange('campaignFieldValue', parseInt(e.target.value) || 0)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" min="0" />
                </div>
              </div>
            </div>
          )}

          {condition.type === 'client_field' && (
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">Champ client</label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Operateur</label>
                  <select value={condition.operator || '='} onChange={(e) => onChange('operator', e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    {OPERATORS_WITH_NEQ.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Valeur</label>
                  <input type="text" value={condition.clientFieldValue || ''} onChange={(e) => onChange('clientFieldValue', e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </div>
              </div>
            </div>
          )}
        </div>
        <button type="button" onClick={() => onRemoveCondition(blockId, parentId, condition.id)} className="mt-1 rounded p-1 text-red-600 hover:bg-red-50">
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
