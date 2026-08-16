export const OBJECTIF_KEY = '_objectif_campagnes_';

export type ObjectifMode = 'atteint' | 'non_atteint';

export const OBJECTIF_MODES: readonly ObjectifMode[] = ['atteint', 'non_atteint'];

export const isObjectifMode = (value: unknown): value is ObjectifMode =>
  OBJECTIF_MODES.includes(value as ObjectifMode);

export const objectifModeLabel = (mode: string | null | undefined): string => {
  if (mode === 'atteint') return 'Abouti';
  if (mode === 'non_atteint') return 'Non abouti';
  return mode || '-';
};

export const objectifModeReadOnlyClasses = (mode: string | null | undefined): string => {
  if (mode === 'atteint') return 'bg-green-100 text-green-800 border-green-200';
  if (mode === 'non_atteint') return 'bg-orange-100 text-orange-800 border-orange-200';
  return 'bg-gray-100 text-gray-700 border-gray-200';
};
