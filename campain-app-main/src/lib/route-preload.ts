export const routeLoaders = {
  campagnes: () => import('@/pages/CampagnesPage'),
  modeles: () => import('@/pages/ModelesPage'),
  createModele: () => import('@/pages/CreateModelePage'),
  viewModele: () => import('@/pages/ViewModelePage'),
  cibles: () => import('@/pages/CiblesPage'),
  createCible: () => import('@/pages/CreateCiblePage'),
  viewCible: () => import('@/pages/ViewCiblePage'),
  clients: () => import('@/pages/ClientsPage'),
  createClient: () => import('@/pages/CreateClientPage'),
  viewClient: () => import('@/pages/ViewClientPage'),
  crc: () => import('@/pages/CRCPage'),
  historique: () => import('@/pages/HistoriquePage'),
  dashboard: () => import('@/pages/DashboardPage'),
  segmentation: () => import('@/pages/SegmentationPage'),
  attrition: () => import('@/pages/AttritionPage'),
};

type RouteLoaderKey = keyof typeof routeLoaders;

const pathToLoader: Array<[RegExp, RouteLoaderKey]> = [
  [/^\/campagnes/, 'campagnes'],
  [/^\/modeles\/create/, 'createModele'],
  [/^\/modeles\/[^/]+\/edit/, 'createModele'],
  [/^\/modeles\/[^/]+\/view/, 'viewModele'],
  [/^\/modeles/, 'modeles'],
  [/^\/cibles\/create/, 'createCible'],
  [/^\/cibles\/[^/]+\/edit/, 'createCible'],
  [/^\/cibles\/[^/]+\/view/, 'viewCible'],
  [/^\/cibles/, 'cibles'],
  [/^\/clients\/create/, 'createClient'],
  [/^\/clients\/[^/]+\/edit/, 'createClient'],
  [/^\/clients\/[^/]+\/view/, 'viewClient'],
  [/^\/clients/, 'clients'],
  [/^\/crc/, 'crc'],
  [/^\/historique/, 'historique'],
  [/^\/dashboard/, 'dashboard'],
  [/^\/outils-data\/segmentation/, 'segmentation'],
  [/^\/outils-data\/attrition/, 'attrition'],
];

const preloaded = new Set<RouteLoaderKey>();

export function preloadRoute(path: string) {
  const match = pathToLoader.find(([pattern]) => pattern.test(path));
  if (!match) return;
  const key = match[1];
  if (preloaded.has(key)) return;
  preloaded.add(key);
  void routeLoaders[key]().catch(() => preloaded.delete(key));
}
