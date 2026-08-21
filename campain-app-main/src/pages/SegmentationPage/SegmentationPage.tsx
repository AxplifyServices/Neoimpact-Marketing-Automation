import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  CalendarDays,
  CircleDollarSign,
  Database,
  RefreshCcw,
  TrendingUp,
  Users,
  WalletCards,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import LoadingSpinner from '@/components/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { getApiClient } from '@/lib/api/api-client';
import { segmentationApi } from '@/lib/api/definitions/segmentation.api';
import type {
  SegmentationDashboardResponse,
  SegmentationFiltersResponse,
} from '@/types/segmentation.types';

const SEGMENT_COLORS: Record<string, string> = {
  'Mass Market': '#64748b',
  Medium: '#2563eb',
  'Haut de gamme': '#7c3aed',
  Premium: '#d97706',
  'Banque privée': '#0f172a',
};

const formatMonth = (value: number) => {
  const raw = String(value);
  return raw.length === 6 ? `${raw.slice(4, 6)}/${raw.slice(0, 4)}` : raw;
};

const formatCount = (value: number) =>
  new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(value || 0);

const formatPercent = (value: number) => `${(value || 0).toFixed(1)} %`;

const formatMoney = (value: number) =>
  `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(value || 0)} MAD`;

interface KpiCardProps {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ReactNode;
}

function KpiCard({ title, value, subtitle, icon }: KpiCardProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{title}</p>
          <p className="mt-2 text-xl font-semibold text-gray-900 sm:text-2xl">{value}</p>
          <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
        </div>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
          {icon}
        </div>
      </div>
    </div>
  );
}

export default function SegmentationPage() {
  const apiClient = getApiClient();
  const [anneeMois, setAnneeMois] = useState<number | null>(null);
  const [region, setRegion] = useState('');
  const [trancheAge, setTrancheAge] = useState('');

  const filtersQuery = useQuery<SegmentationFiltersResponse>({
    queryKey: ['segmentation', 'filters'],
    queryFn: () => apiClient.request(segmentationApi.filters()),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (anneeMois === null && filtersQuery.data?.default_annee_mois) {
      setAnneeMois(filtersQuery.data.default_annee_mois);
    }
  }, [anneeMois, filtersQuery.data?.default_annee_mois]);

  const dashboardQuery = useQuery<SegmentationDashboardResponse>({
    queryKey: ['segmentation', 'dashboard', anneeMois, region, trancheAge],
    queryFn: () => apiClient.request(
      segmentationApi.dashboard({
        annee_mois: anneeMois!,
        ...(region ? { region } : {}),
        ...(trancheAge ? { tranche_age: trancheAge } : {}),
      })
    ),
    enabled: anneeMois !== null,
    staleTime: 60 * 1000,
  });

  const segmentData = useMemo(
    () => (dashboardQuery.data?.segments ?? []).filter((item) => item.clients > 0),
    [dashboardQuery.data?.segments]
  );
  const salaryData = dashboardQuery.data?.statuts_salarie ?? [];
  const kpis = dashboardQuery.data?.kpis;

  const resetFilters = () => {
    setAnneeMois(filtersQuery.data?.default_annee_mois ?? null);
    setRegion('');
    setTrancheAge('');
  };

  return (
    <div className="min-h-screen bg-gray-50 p-4 pt-20 sm:p-6 sm:pt-20 lg:p-8 lg:pt-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              <Database className="h-4 w-4" />
              Outils data
            </div>
            <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Segmentation</h1>
            <p className="mt-1 max-w-2xl text-sm text-gray-600">
              Suivez la répartition des segments, les médianes de référence et les principaux indicateurs du moteur de segmentation.
            </p>
          </div>
          {kpis?.derniere_date_segmentation && (
            <div className="text-xs text-gray-500 sm:text-right">
              Dernier calcul de la période<br />
              <span className="font-medium text-gray-800">{kpis.derniere_date_segmentation}</span>
            </div>
          )}
        </div>

        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-[1fr_1.25fr_1fr_auto] lg:items-end">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Mois / année</label>
              <select
                value={anneeMois ?? ''}
                onChange={(event) => setAnneeMois(Number(event.target.value))}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
              >
                {(filtersQuery.data?.annee_mois ?? []).map((month) => (
                  <option key={month} value={month}>{formatMonth(month)}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Région</label>
              <select
                value={region}
                onChange={(event) => setRegion(event.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
              >
                <option value="">Toutes les régions</option>
                {(filtersQuery.data?.regions ?? []).map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Âge</label>
              <select
                value={trancheAge}
                onChange={(event) => setTrancheAge(event.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
              >
                <option value="">Toutes les tranches</option>
                {(filtersQuery.data?.tranches_age ?? []).map((value) => (
                  <option key={value} value={value}>{value} ans</option>
                ))}
              </select>
            </div>

            <Button variant="outline" onClick={resetFilters} className="w-full lg:w-auto">
              <RefreshCcw className="mr-2 h-4 w-4" />
              Réinitialiser
            </Button>
          </div>
        </div>

        {(filtersQuery.isLoading || (dashboardQuery.isLoading && !dashboardQuery.data)) && (
          <div className="flex min-h-[45vh] items-center justify-center">
            <LoadingSpinner size="lg" />
          </div>
        )}

        {(filtersQuery.error || dashboardQuery.error) && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Impossible de charger le tableau de bord de segmentation.
          </div>
        )}

        {dashboardQuery.data && kpis && (
          <>
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
              <KpiCard title="Clients segmentés" value={formatCount(kpis.clients_segmentes)} subtitle="Photo au mois sélectionné" icon={<Users className="h-4 w-4" />} />
              <KpiCard title="Calculs période" value={formatCount(kpis.calculs_periode)} subtitle="Résultats produits ce mois" icon={<CalendarDays className="h-4 w-4" />} />
              <KpiCard title="Salariés" value={formatPercent(kpis.taux_salaries)} subtitle="Fréquence + régularité" icon={<Activity className="h-4 w-4" />} />
              <KpiCard title="Haut potentiel" value={formatPercent(kpis.taux_haut_potentiel)} subtitle="Haut de gamme, Premium, BP" icon={<TrendingUp className="h-4 w-4" />} />
              <KpiCard title="Flux moyen 3 mois" value={formatMoney(kpis.flux_moyen_3m)} subtitle="Flux créditeurs lissés" icon={<CircleDollarSign className="h-4 w-4" />} />
              <KpiCard title="Avoir moyen 3 mois" value={formatMoney(kpis.avoir_moyen_3m)} subtitle="Avoir retenu selon le statut" icon={<WalletCards className="h-4 w-4" />} />
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <div className="mb-4">
                  <h2 className="text-base font-semibold text-gray-900">Répartition des segments</h2>
                  <p className="text-xs text-gray-500">Dernier segment connu de chaque client à la période sélectionnée.</p>
                </div>
                <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-[1fr_180px]">
                  <div className="space-y-2">
                    {segmentData.map((item) => (
                      <div key={item.segment} className="flex items-center justify-between gap-3 text-sm">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: SEGMENT_COLORS[item.segment] ?? '#94a3b8' }} />
                          <span className="truncate text-gray-700">{item.segment}</span>
                        </div>
                        <div className="shrink-0 text-right">
                          <span className="font-medium text-gray-900">{formatCount(item.clients)}</span>
                          <span className="ml-2 text-xs text-gray-500">{formatPercent(item.part)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="h-44">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={segmentData} dataKey="clients" nameKey="segment" innerRadius={44} outerRadius={70} paddingAngle={2} strokeWidth={0}>
                          {segmentData.map((item) => (
                            <Cell key={item.segment} fill={SEGMENT_COLORS[item.segment] ?? '#94a3b8'} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(value) => formatCount(Number(value))} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <div className="mb-4">
                  <h2 className="text-base font-semibold text-gray-900">Statut salarié détecté</h2>
                  <p className="text-xs text-gray-500">Classification utilisée pour choisir la méthode de calcul des avoirs.</p>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={salaryData} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="statut" tick={{ fontSize: 11 }} interval={0} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(value) => formatCount(Number(value))} width={70} />
                      <Tooltip formatter={(value) => formatCount(Number(value))} />
                      <Bar dataKey="clients" fill="#334155" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 p-4">
                <h2 className="text-base font-semibold text-gray-900">Médianes de référence</h2>
                <p className="mt-1 text-xs text-gray-500">Médianes réellement utilisées par le moteur pour chaque couple région × tranche d'âge.</p>
              </div>
              <div className="max-h-[520px] overflow-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <thead className="sticky top-0 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">Région</th>
                      <th className="px-4 py-3 font-medium">Âge</th>
                      <th className="px-4 py-3 text-right font-medium">Médiane flux</th>
                      <th className="px-4 py-3 text-right font-medium">Médiane avoirs</th>
                      <th className="px-4 py-3 text-right font-medium">Clients calculés</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {dashboardQuery.data.medianes.map((row) => (
                      <tr key={`${row.region}-${row.tranche_age}`} className="hover:bg-gray-50">
                        <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">{row.region}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-gray-700">{row.tranche_age} ans</td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-gray-700">{formatMoney(row.mediane_flux)}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-gray-700">{formatMoney(row.mediane_avoirs)}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-gray-700">{formatCount(row.observations)}</td>
                      </tr>
                    ))}
                    {dashboardQuery.data.medianes.length === 0 && (
                      <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-500">Aucune médiane disponible pour ces filtres.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
