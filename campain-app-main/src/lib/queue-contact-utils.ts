export const normalizeKey = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, '');

export const formatKeyLabel = (key: string) =>
  key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();

export const getKeyRank = (key: string) => {
  const normalized = normalizeKey(key);
  if (normalized.includes('prenom') || normalized.includes('firstname')) return 0;
  if (normalized.includes('nom') || normalized.includes('lastname') || normalized.includes('name')) return 1;
  if (normalized.includes('telephone') || normalized.includes('tel') || normalized.includes('mobile') || normalized.includes('gsm')) return 2;
  if (normalized.includes('email') || normalized.includes('mail')) return 3;
  if (normalized.includes('adresse') || normalized.includes('address')) return 4;
  if (normalized.includes('idcampagne')) return 5;
  if (normalized.includes('radicalcompte') || normalized.includes('radical')) return 6;
  if (normalized.startsWith('id')) return 7;
  return 10;
};
