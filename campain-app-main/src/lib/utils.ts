import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function getPageNumbers(currentPage: number, totalPages: number): (number | string)[] {
  const delta = 2
  const range: (number | string)[] = []
  const rangeWithDots: (number | string)[] = []

  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= currentPage - delta && i <= currentPage + delta)) {
      range.push(i)
    }
  }

  let prev: number | undefined
  for (const i of range) {
    if (prev !== undefined && (i as number) - prev > 1) {
      rangeWithDots.push('...')
    }
    rangeWithDots.push(i)
    prev = i as number
  }

  return rangeWithDots
}

// Objectif parsing utilities
export type ParsedObjectifItem = {
  variable?: string;
  type: 'cat' | 'num';
  value?: string;
  min?: number;
  max?: number;
  label: string;
};

export type ParsedObjectif =
  | { kind: 'empty' }
  | { kind: 'single'; item: ParsedObjectifItem }
  | { kind: 'multi'; op: 'AND' | 'OR'; items: ParsedObjectifItem[] };

const toNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && !Number.isNaN(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
};

const formatRangeLabel = (min: number | null, max: number | null): string => {
  if (min !== null && max !== null) return `${min} - ${max}`;
  if (min !== null) return `>= ${min}`;
  if (max !== null) return `<= ${max}`;
  return '';
};

export function parseObjectif(raw: string): ParsedObjectif {
  if (!raw || raw.trim() === '') {
    return { kind: 'empty' };
  }

  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      // Multi-objectif format: { op: 'AND'|'OR', items: [...] }
      if (parsed.op && Array.isArray(parsed.items)) {
        const items: ParsedObjectifItem[] = parsed.items.map((item: any) => {
          if (item.type === 'num') {
            const min = toNumber(item.min);
            const max = toNumber(item.max);
            return {
              variable: item.variable,
              type: 'num' as const,
              min: min ?? undefined,
              max: max ?? undefined,
              label: formatRangeLabel(min, max),
            };
          }
          return {
            variable: item.variable,
            type: 'cat' as const,
            value: item.value,
            label: item.value || '',
          };
        });
        return { kind: 'multi', op: parsed.op, items };
      }

      // Single numeric: { min, max }
      const min = toNumber(parsed.min);
      const max = toNumber(parsed.max);
      if (min !== null || max !== null) {
        return {
          kind: 'single',
          item: {
            type: 'num',
            min: min ?? undefined,
            max: max ?? undefined,
            label: formatRangeLabel(min, max),
          },
        };
      }
    }
  } catch {
    // Not JSON
  }

  // Plain text value
  return {
    kind: 'single',
    item: { type: 'cat', value: raw, label: raw },
  };
}

export function formatObjectifSummary(parsed: ParsedObjectif): string {
  if (parsed.kind === 'empty') return 'Non défini';
  if (parsed.kind === 'single') {
    const { item } = parsed;
    if (item.variable) {
      return `${item.variable}: ${item.label}`;
    }
    return item.label;
  }
  // Multi
  const labels = parsed.items.map(item =>
    item.variable ? `${item.variable}: ${item.label}` : item.label
  );
  return labels.join(` ${parsed.op} `);
}
