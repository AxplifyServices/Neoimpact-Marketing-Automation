import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Gauge,
  Layers3,
  RefreshCcw,
  ShieldAlert,
  Users,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import LoadingSpinner from '@/components/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { getApiClient } from '@/lib/api/api-client';
import { commercialPressureApi } from '@/lib/api/definitions/commercial-pressure.api';
import type {
  CommercialPressureDashboardResponse,
  CommercialPressureFiltersResponse,
} from '@/types/commercial-pressure.types';

const formatCount = (value?: number | null) => Number(value ?? 0).toLocaleString('fr-FR');
const formatScore = (value?: number | null) => Number(value ?? 0).toFixed(2);
const formatPercent = (value?: number | null) => `${Number(value ?? 0).toFixed(1)} %`;
const formatMonth = (value: number) => {
  const year = Math.floor(value / 100);
  const month = value % 100;
  return new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric' }).format(new Date(year, month - 1, 1));
};

function KpiCard({ title, value, subtitle, icon }: { title: string; value: string; subtitle: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-gray-500">{title}</p>
          <p className="mt-1 text-xl font-bold text-gray-900">{value}</p>
          <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
        </div>
        <div className="rounded-lg bg-slate-100 p-2 text-slate-700">{icon}</div>
      </div>
    </div>
  );
}

const ruleLabel = (value: string) => ({
  score: 'Score pondéré',
  actions_7j: '6+ actions / 7 jours',
  actions_30j: '10+ actions / 30 jours',
  humain_7j: '4+ contacts humains / 7 jours',
  canaux_7j: '4+ canaux / 7 jours',
  actions_7j_minimum: '4+ actions / 7 jours',
}[value] ?? value);

export default function CommercialPressurePage() {
  const apiClient = getApiClient();
  const [anneeMois, setAnneeMois] = useState<number | null>(null);
  const [region, setRegion] = useState('');
  const [statut, setStatut] = useState('');
  const [niveau, setNiveau] = useState('');

  const filtersQuery = useQuery<CommercialPressureFiltersResponse>({
    queryKey: ['commercial-pressure', 'filters'],
    queryFn: () => apiClient.request(commercialPressureApi.filters()),
    staleTime: 5 * 60 * 1000,
    refetchInterval: anneeMois === null ? 30_000 : false,
  });

  useEffect(() => {
    if (anneeMois === null && filtersQuery.data?.default_annee_mois) {
      setAnneeMois(filtersQuery.data.default_annee_mois);
    }
  }, [anneeMois, filtersQuery.data?.default_annee_mois]);

  const dashboardQuery = useQuery<CommercialPressureDashboardResponse>({
    queryKey: ['commercial-pressure', 'dashboard', anneeMois, region, statut, niveau],
    queryFn: () => apiClient.request(commercialPressureApi.dashboard({
      annee_mois: anneeMois ?? undefined,
      region: region || undefined,
      statut_client: statut || undefined,
      niveau: niveau || undefined,
    })),
    enabled: anneeMois !== null,
    staleTime: 60 * 1000,
  });

  const summary = dashboardQuery.data?.summary;
  const resetFilters = () => {
    setAnneeMois(filtersQuery.data?.default_annee_mois ?? null);
    setRegion('');
    setStatut('');
    setNiveau('');
  };

  return (
    <div className="min-h-screen bg-gray-50 p-3 pt-16 sm:p-4 sm:pt-16 lg:p-6 lg:pt-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-600">
              <Gauge className="h-4 w-4" />
              Outils data
            </div>
            <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Pression commerciale</h1>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Mesurez la sursollicitation sur les 30 derniers jours selon le canal, la récence, l'exposition réelle et les répétitions rapprochées.
            </p>
          </div>
          {summary?.last_scoring && (
            <div className="text-xs text-gray-500 sm:text-right">
              Dernier calcul<br />
              <span className="font-medium text-gray-800">{summary.last_scoring}</span>
            </div>
          )}
        </div>

        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-[1fr_1.2fr_1fr_1fr_auto] xl:items-end">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Mois / année</label>
              <select value={anneeMois ?? ''} onChange={(e) => setAnneeMois(Number(e.target.value))} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
                {(filtersQuery.data?.months ?? []).map((month) => <option key={month} value={month}>{formatMonth(month)}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Région</label>
              <select value={region} onChange={(e) => setRegion(e.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
                <option value="">Toutes les régions</option>
                {(filtersQuery.data?.regions ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Statut client</label>
              <select value={statut} onChange={(e) => setStatut(e.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
                <option value="">Actifs + inactifs</option>
                {(filtersQuery.data?.statuses ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Niveau</label>
              <select value={niveau} onChange={(e) => setNiveau(e.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
                <option value="">Tous les niveaux</option>
                {(filtersQuery.data?.levels ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <Button variant="outline" onClick={resetFilters} className="w-full xl:w-auto"><RefreshCcw className="mr-2 h-4 w-4" />Réinitialiser</Button>
          </div>
        </div>

        {filtersQuery.isLoading && <div className="flex min-h-[45vh] items-center justify-center"><LoadingSpinner size="lg" /></div>}
        {!filtersQuery.isLoading && (filtersQuery.data?.months?.length ?? 0) === 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">Aucun calcul de pression commerciale n'est encore disponible.</div>
        )}
        {(filtersQuery.error || dashboardQuery.error) && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">Impossible de charger le tableau de bord de pression commerciale.</div>
        )}
        {dashboardQuery.isLoading && !dashboardQuery.data && <div className="flex min-h-[45vh] items-center justify-center"><LoadingSpinner size="lg" /></div>}

        {dashboardQuery.data && summary && (
          <>
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
              <KpiCard title="Clients scorés" value={formatCount(summary.scored_clients)} subtitle="Actifs et inactifs" icon={<Users className="h-4 w-4" />} />
              <KpiCard title="Pression élevée" value={formatCount(summary.high_clients)} subtitle={formatPercent(summary.high_rate)} icon={<ShieldAlert className="h-4 w-4" />} />
              <KpiCard title="Score moyen" value={formatScore(summary.avg_score)} subtitle="Seuil élevé à partir de 8" icon={<Gauge className="h-4 w-4" />} />
              <KpiCard title="Actions / 7 j" value={formatScore(summary.avg_actions_7d)} subtitle="Moyenne par client" icon={<AlertTriangle className="h-4 w-4" />} />
              <KpiCard title="Actions / 30 j" value={formatScore(summary.avg_actions_30d)} subtitle="Fenêtre de calcul" icon={<Layers3 className="h-4 w-4" />} />
              <KpiCard title="Canaux / 7 j" value={formatScore(summary.avg_channels_7d)} subtitle="Diversité récente" icon={<Layers3 className="h-4 w-4" />} />
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Répartition de la pression</h2>
                <p className="mb-4 text-xs text-gray-500">Faible, modérée et élevée selon les seuils métier.</p>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dashboardQuery.data.distribution}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="niveau" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatCount(Number(value))} />
                      <Bar dataKey="clients" name="Clients" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Déclencheurs de vigilance</h2>
                <p className="mb-4 text-xs text-gray-500">Règles ayant conduit à un niveau modéré ou élevé.</p>
                <div className="space-y-3">
                  {dashboardQuery.data.rules.length > 0 ? dashboardQuery.data.rules.map((row) => (
                    <div key={row.regle} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-medium text-gray-800">{ruleLabel(row.regle)}</span>
                        <span className="text-sm font-semibold text-gray-900">{formatCount(row.clients)}</span>
                      </div>
                    </div>
                  )) : <p className="text-sm text-gray-500">Aucun déclencheur sur la sélection.</p>}
                </div>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 p-4">
                <h2 className="text-base font-semibold text-gray-900">Pression commerciale par région</h2>
                <p className="text-xs text-gray-500">Part des clients en pression élevée et volume moyen de sollicitations.</p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th className="px-4 py-3">Région</th>
                      <th className="px-4 py-3">Clients</th>
                      <th className="px-4 py-3">Élevé</th>
                      <th className="px-4 py-3">Part élevée</th>
                      <th className="px-4 py-3">Score moyen</th>
                      <th className="px-4 py-3">Actions / 30 j</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {dashboardQuery.data.regions.map((row) => (
                      <tr key={row.region}>
                        <td className="px-4 py-3 font-medium text-gray-900">{row.region}</td>
                        <td className="px-4 py-3 text-gray-700">{formatCount(row.clients)}</td>
                        <td className="px-4 py-3 text-gray-700">{formatCount(row.high_clients)}</td>
                        <td className="px-4 py-3 text-gray-700">{formatPercent(row.high_rate)}</td>
                        <td className="px-4 py-3 text-gray-700">{formatScore(row.avg_score)}</td>
                        <td className="px-4 py-3 text-gray-700">{formatScore(row.avg_actions_30d)}</td>
                      </tr>
                    ))}
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
