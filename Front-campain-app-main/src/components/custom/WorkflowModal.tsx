import { useMemo } from 'react';
import { X } from 'lucide-react';
import WorkflowPreview from './WorkflowPreview';

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
  daysSinceLastAction?: number | string;
  flagResultat?: string;
  counterValue?: number | string;
  campaignField?: string;
  campaignFieldValue?: number;
  clientField?: string;
  clientFieldValue?: string;
  fieldLabel?: string;
  nextBlockId: string | null;
}

interface WorkflowModalProps {
  isOpen: boolean;
  onClose: () => void;
  campaignId?: string;
  listeActionJson: string;
  variableCible: string;
  objectif: string;
  campaignTitle: string;
}

export default function WorkflowModal({
  isOpen,
  onClose,
  campaignId,
  listeActionJson,
}: WorkflowModalProps) {
  const blocks = useMemo(() => {
    if (!listeActionJson) return [];

    try {
      const parsed = JSON.parse(listeActionJson);
      if (!Array.isArray(parsed) || parsed.length === 0) return [];

      const isOldFormat =
        'ID' in parsed[0] ||
        'Bloc_mere' in parsed[0] ||
        'Bloc_m\u00e8re' in parsed[0] ||
        'Bloc_mA"re' in parsed[0] ||
        'Canal' in parsed[0];
      if (!isOldFormat) {
        return parsed as Block[];
      }

      const normalizeField = (value: string): string =>
        value
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '')
          .toLowerCase();

      const getFieldKind = (value: string): ConditionType | 'unknown' => {
        const normalized = normalizeField(value);
        if (normalized.startsWith('flag')) {
          return 'flag_resultat';
        }
        if (normalized.includes('days_since_last_action') || normalized.includes('nb jours depuis last action')) {
          return 'days_since_last';
        }
        // Check nb_jour_debut_campagne BEFORE nb_ to avoid wrong match
        if (normalized === 'nb_jour_debut_campagne') {
          return 'campaign_field';
        }
        if (normalized.startsWith('client.')) {
          return 'client_field';
        }
        if (normalized.includes('nb_') || normalized.startsWith('nb ') || normalized === 'counter') {
          return 'counter';
        }
        return 'unknown';
      };

      return parsed.map((oldBlock: any, index: number) => {
        const parentValue =
          oldBlock['Bloc_mere'] ??
          oldBlock['Bloc_m\u00e8re'] ??
          oldBlock['Bloc_mA"re'] ??
          oldBlock.parentBlockId ??
          null;

        return {
          id: `block_${oldBlock.ID ?? index}`,
          canal: oldBlock.Canal || '',
          delai: 0,
          parentBlockId: parentValue ? `block_${parentValue}` : null,
          objet: oldBlock.Objet || '',
          contenu: oldBlock.Contenu || '',
          conditions: (oldBlock.Conditions || []).map((oldCond: any, condIndex: number) => {
            const condition: BlockCondition = {
              id: `cond_${oldBlock.ID ?? index}_${condIndex}`,
              type: 'flag_resultat',
              nextBlockId: null,
            };

            const fieldLabel = typeof oldCond.field === 'string' ? oldCond.field : '';
            const fieldKind = fieldLabel ? getFieldKind(fieldLabel) : 'unknown';

            if (fieldKind === 'flag_resultat') {
              condition.type = 'flag_resultat';
              condition.flagResultat = oldCond.value;
              condition.operator = oldCond.op || '=';
            } else if (fieldKind === 'days_since_last') {
              condition.type = 'days_since_last';
              condition.daysSinceLastAction = oldCond.value;
              condition.operator = oldCond.op || '>';
            } else if (fieldKind === 'counter') {
              condition.type = 'counter';
              condition.counterValue = oldCond.value;
              condition.operator = oldCond.op || '>';
            } else if (fieldKind === 'campaign_field') {
              condition.type = 'campaign_field';
              condition.campaignField = oldCond.field;
              condition.campaignFieldValue = oldCond.value;
              condition.operator = oldCond.op || '>=';
            } else if (fieldKind === 'client_field') {
              condition.type = 'client_field';
              condition.clientField = oldCond.field?.replace('client.', '');
              condition.clientFieldValue = oldCond.value;
              condition.operator = oldCond.op || '=';
            } else if (fieldLabel) {
              condition.type = 'counter';
              condition.counterValue = oldCond.value;
              condition.operator = oldCond.op || '=';
            }

            if (fieldLabel) {
              condition.fieldLabel = fieldLabel;
            }

            if (oldCond.next_block_id) {
              condition.nextBlockId = `block_${oldCond.next_block_id}`;
            }

            return condition;
          }),
        };
      });
    } catch {
      return [];
    }
  }, [listeActionJson]);

  const blockDisplayMap = useMemo(() => {
    const ordered: Block[] = [];

    const addBlockAndChildren = (blockId: string | null) => {
      const children = blocks.filter(block => block.parentBlockId === blockId);
      children.forEach(child => {
        ordered.push(child);
        addBlockAndChildren(child.id);
      });
    };

    const roots = blocks.filter(block => block.parentBlockId === null);
    roots.forEach(root => {
      ordered.push(root);
      addBlockAndChildren(root.id);
    });

    return new Map(ordered.map((block, index) => [block.id, index + 1]));
  }, [blocks]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full h-full max-w-[95vw] max-h-[95vh] overflow-hidden relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 z-10 p-2 bg-white/80 hover:bg-white rounded-full shadow-sm transition-colors cursor-pointer"
          aria-label="Fermer"
        >
          <X className="w-6 h-6 text-gray-600" />
        </button>

        {/* Workflow Content - Full height */}
        <div className="w-full h-full">
          <div className="w-full h-full">
            {blocks.length === 0 ? (
              <div className="h-full bg-gray-100 flex items-center justify-center rounded">
                <span className="text-gray-400 text-sm">Aucun workflow disponible</span>
              </div>
            ) : (
              <WorkflowPreview
                blocks={blocks}
                getBlockDisplayNumber={(id) => blockDisplayMap.get(id) ?? 0}
                campaignId={campaignId}
                fitViewSignal={blocks.length}
                modalOpen={isOpen}
                showHeader={false}
                showFrame={false}
                containerClassName="h-full"
                height="100%"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
