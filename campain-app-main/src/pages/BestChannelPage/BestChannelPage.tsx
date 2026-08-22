import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BrainCircuit,
  CalendarDays,
  RadioTower,
  RefreshCcw,
  Target,
  TrendingUp,
  Users,
  Waypoints,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import LoadingSpinner from '@/components/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { getApiClient } from '@/lib/api/api-client';
import { bestChannelApi } from '@/lib/api/definitions/best-channel.api';
import type {
  BestChannelDashboardResponse,
  BestChannelFiltersResponse,
} from '@/types/best-channel.types';

const formatMonth = (value: number) => {
  const raw = String(value);
  return raw.length === 6 ? `${raw.slice(4, 6)}/${raw.slice(0, 4)}` : raw;
};

const formatCount = (value: number) => new Intl.NumberFormat('fr-FR').format(value || 0);
const formatPercent = (value: number) => `${(value || 0).toFixed(1)} %`;
const formatScore = (value: number) => `${((value || 0) * 100).toFixed(1)} %`;

function KpiCard({
  title,
  value,
  subtitle,
  icon,
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ReactNode;
}) {
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

export default function BestChannelPage() {
  const apiClient = getApiClient();
  const [anneeMois, setAnneeMois] = useState<number | null>(null);
  const [region, setRegion] = useState('');
  const [statut, setStatut] = useState('');

  const filtersQuery = useQuery<BestChannelFiltersResponse>({
    queryKey: ['best-channel', 'filters'],
    queryFn: () => apiClient.request(bestChannelApi.filters()),
    staleTime: 5 * 60 * 1000,
    refetchInterval: anneeMois === null ? 30_000 : false,
  });

  useEffect(() => {
    if (anneeMois === null && filtersQuery.data?.default_annee_mois) {
      setAnneeMois(filtersQuery.data.default_annee_mois);
    }
  }, [anneeMois, filtersQuery.data?.default_annee_mois]);

  const dashboardQuery = useQuery<BestChannelDashboardResponse>({
    queryKey: ['best-channel', 'dashboard', anneeMois, region, statut],
    queryFn: () => apiClient.request(
      bestChannelApi.dashboard({
        annee_mois: anneeMois ?? undefined,
        region: region || undefined,
        statut_client: statut || undefined,
      }),
    ),
    enabled: anneeMois !== null,
    staleTime: 60 * 1000,
  });

  const summary = dashboardQuery.data?.summary;
  const resetFilters = () => {
    setAnneeMois(filtersQuery.data?.default_annee_mois ?? null);
    setRegion('');
    setStatut('');
  };

  return (
    <div className="min-h-screen bg-gray-50 p-3 pt-16 sm:p-4 sm:pt-16 lg:p-6 lg:pt-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-600">
              <RadioTower className="h-4 w-4" />
              Outils data
            </div>
            <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Best canal</h1>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Classez les trois canaux les plus susceptibles de contribuer à l'atteinte d'un objectif pour chaque client.
            </p>
          </div>
          {summary?.last_scoring && (
            <div className="text-xs text-gray-500 sm:text-right">
              Dernier scoring<br />
              <span className="font-medium text-gray-800">{summary.last_scoring}</span>
            </div>
          )}
        </div>

        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-[1fr_1.2fr_1fr_auto] lg:items-end">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Mois / année</label>
              <select
                value={anneeMois ?? ''}
                onChange={(e) => setAnneeMois(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
              >
                {(filtersQuery.data?.months ?? []).map((month) => (
                  <option key={month} value={month}>{formatMonth(month)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Région</label>
              <select
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">Toutes les régions</option>
                {(filtersQuery.data?.regions ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Statut client</label>
              <select
                value={statut}
                onChange={(e) => setStatut(e.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">Actifs + inactifs</option>
                {(filtersQuery.data?.statuses ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <Button variant="outline" onClick={resetFilters} className="w-full lg:w-auto">
              <RefreshCcw className="mr-2 h-4 w-4" />Réinitialiser
            </Button>
          </div>
        </div>

        {filtersQuery.isLoading && (
          <div className="flex min-h-[45vh] items-center justify-center"><LoadingSpinner size="lg" /></div>
        )}

        {!filtersQuery.isLoading && (filtersQuery.data?.months?.length ?? 0) === 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            Aucun scoring Best canal n'est encore disponible. Le worker est probablement en cours d'entraînement ou de scoring.
          </div>
        )}

        {(filtersQuery.error || dashboardQuery.error) && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Impossible de charger le tableau de bord Best canal.
          </div>
        )}

        {dashboardQuery.isLoading && !dashboardQuery.data && (
          <div className="flex min-h-[45vh] items-center justify-center"><LoadingSpinner size="lg" /></div>
        )}

        {dashboardQuery.data && summary && (
          <>
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
              <KpiCard title="Clients scorés" value={formatCount(summary.scored_clients)} subtitle="Actifs et inactifs éligibles" icon={<Users className="h-4 w-4" />} />
              <KpiCard title="Score Top 1 moyen" value={formatScore(summary.avg_top1_score)} subtitle="Probabilité moyenne du premier canal" icon={<TrendingUp className="h-4 w-4" />} />
              <KpiCard title="Séquences apprises" value={formatCount(summary.sequences)} subtitle="12 derniers mois" icon={<Waypoints className="h-4 w-4" />} />
              <KpiCard title="Objectifs atteints" value={formatCount(summary.converted_sequences)} subtitle={formatPercent(summary.conversion_rate)} icon={<Target className="h-4 w-4" />} />
              <KpiCard title="AUC validation" value={dashboardQuery.data.model.validation_auc == null ? '—' : dashboardQuery.data.model.validation_auc.toFixed(3)} subtitle="Qualité discriminante du modèle" icon={<BrainCircuit className="h-4 w-4" />} />
              <KpiCard title="Non scorés" value={formatCount(summary.non_scored)} subtitle="Dans la période affichée" icon={<CalendarDays className="h-4 w-4" />} />
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Répartition du canal Top 1</h2>
                <p className="mb-4 text-xs text-gray-500">Canal recommandé en priorité pour les clients scorés.</p>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dashboardQuery.data.top1_distribution}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="canal" tick={{ fontSize: 10 }} interval={0} angle={-18} textAnchor="end" height={70} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip
                        formatter={(value, name) => name === 'clients'
                          ? formatCount(Number(value))
                          : formatScore(Number(value))}
                      />
                      <Bar dataKey="clients" name="Clients" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Présence dans le Top 3</h2>
                <p className="mb-4 text-xs text-gray-500">Nombre d'apparitions de chaque canal aux rangs 1, 2 et 3.</p>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dashboardQuery.data.top3_distribution}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="canal" tick={{ fontSize: 10 }} interval={0} angle={-18} textAnchor="end" height={70} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatCount(Number(value))} />
                      <Legend />
                      <Bar dataKey="top1" name="Top 1" />
                      <Bar dataKey="top2" name="Top 2" />
                      <Bar dataKey="top3" name="Top 3" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-[1.45fr_1fr]">
              <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                <div className="border-b border-gray-100 p-4">
                  <h2 className="text-base font-semibold text-gray-900">Best canal par région</h2>
                  <p className="text-xs text-gray-500">Canal Top 1 dominant et score moyen par région.</p>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                      <tr>
                        <th className="px-4 py-3">Région</th>
                        <th className="px-4 py-3">Clients</th>
                        <th className="px-4 py-3">Canal dominant</th>
                        <th className="px-4 py-3">Part dominante</th>
                        <th className="px-4 py-3">Score moyen</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {dashboardQuery.data.regions.map((item) => (
                        <tr key={item.region}>
                          <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">{item.region}</td>
                          <td className="px-4 py-3 text-gray-600">{formatCount(item.clients_scores)}</td>
                          <td className="px-4 py-3 text-gray-600">{item.dominant_channel || '—'}</td>
                          <td className="px-4 py-3 text-gray-600">
                            {formatPercent(item.clients_scores ? item.dominant_clients / item.clients_scores * 100 : 0)}
                          </td>
                          <td className="px-4 py-3 text-gray-600">{formatScore(item.avg_top1_score)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Modèle et historique</h2>
                <div className="mt-4 space-y-3 text-sm">
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Statut modèle</span><span className="font-medium text-gray-900">{dashboardQuery.data.model.exists ? 'Disponible' : 'Absent'}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Version</span><span className="break-all text-right font-medium text-gray-900">{dashboardQuery.data.model.model_code || '—'}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Lignes entraînement</span><span className="font-medium text-gray-900">{formatCount(dashboardQuery.data.model.training_rows ?? 0)}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Blocs historiques</span><span className="font-medium text-gray-900">{formatCount(dashboardQuery.data.training.interaction_rows)}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Blocs fake</span><span className="font-medium text-gray-900">{formatCount(dashboardQuery.data.training.fake_rows)}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Blocs réels</span><span className="font-medium text-gray-900">{formatCount(dashboardQuery.data.training.real_rows)}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">AUC validation</span><span className="font-medium text-gray-900">{dashboardQuery.data.model.validation_auc == null ? '—' : dashboardQuery.data.model.validation_auc.toFixed(3)}</span></div>
                  <div className="border-t border-gray-100 pt-3 text-xs text-gray-500">
                    Le scoring est recalculé pour les nouveaux clients et pour ceux dont le dernier score date de six mois ou plus.
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
