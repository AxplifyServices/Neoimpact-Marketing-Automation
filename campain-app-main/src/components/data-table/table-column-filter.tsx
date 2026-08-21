import { Input } from '@/components/ui/input';
import { MultiSelect } from '@/components/ui/multi-select';
import type { TableFilterOptionMeta } from '@/pages/HistoriquePage/useHistoriqueData';

export type TableColumnFilterValue =
  | { categorical: string[] }
  | { numeric: { min?: number; max?: number } }
  | { text: string };

type Props = {
  columnName: string;
  meta?: TableFilterOptionMeta;
  value?: TableColumnFilterValue;
  onChange: (value?: TableColumnFilterValue) => void;
};

export function TableColumnFilter({ columnName, meta, value, onChange }: Props) {
  const kind = meta?.kind ?? 'text';

  if (kind === 'numeric') {
    const current = 'numeric' in (value ?? {}) ? (value as { numeric: { min?: number; max?: number } }).numeric : {};
    const update = (next: { min?: number; max?: number }) => {
      if (next.min === undefined && next.max === undefined) onChange(undefined);
      else onChange({ numeric: next });
    };
    return (
      <div className="flex min-w-[150px] gap-1">
        <Input
          type="number"
          inputMode="decimal"
          placeholder="Min"
          value={current.min ?? ''}
          onChange={(event) => update({ ...current, min: event.target.value === '' ? undefined : Number(event.target.value) })}
          className="h-8 min-w-[68px] text-xs"
          aria-label={`${columnName} minimum`}
        />
        <Input
          type="number"
          inputMode="decimal"
          placeholder="Max"
          value={current.max ?? ''}
          onChange={(event) => update({ ...current, max: event.target.value === '' ? undefined : Number(event.target.value) })}
          className="h-8 min-w-[68px] text-xs"
          aria-label={`${columnName} maximum`}
        />
      </div>
    );
  }

  if (kind === 'categorical') {
    const selected = 'categorical' in (value ?? {}) ? (value as { categorical: string[] }).categorical : [];
    const options = (meta?.options ?? []).map((item) => ({ value: item, label: item }));
    return (
      <div className="min-w-[170px] max-w-[240px]">
        <MultiSelect
          options={options}
          selected={selected}
          onChange={(next) => onChange(next.length ? { categorical: next } : undefined)}
          placeholder="Choisir..."
        />
      </div>
    );
  }

  const text = 'text' in (value ?? {}) ? (value as { text: string }).text : '';
  return (
    <Input
      type="search"
      placeholder="Contient..."
      value={text}
      onChange={(event) => onChange(event.target.value ? { text: event.target.value } : undefined)}
      className="h-8 min-w-[150px] text-xs"
      aria-label={`Filtrer ${columnName}`}
    />
  );
}
