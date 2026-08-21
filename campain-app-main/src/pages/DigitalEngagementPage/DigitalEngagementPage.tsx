import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Clock3,
  RefreshCcw,
  Smartphone,
  TrendingUp,
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
import { digitalEngagementApi } from '@/lib/api/definitions/digital-engagement.api';
import type {
  DigitalEngagementDashboardResponse,
  DigitalEngagementFiltersResponse,
} from '@/types/digital-engagement.types';

const formatMonth = (value: number) => {
  const raw = String(value);
  return raw.length === 6 ? `${raw.slice(4, 6)}/${raw.slice(0, 4)}` : raw;
};

const formatCount = (value: number) => new Intl.NumberFormat('fr-FR').format(value || 0);
const formatPercent = (value: number) => `${(value || 0).toFixed(1)} %`;
const formatHour = (value: number | null) => {
  if (value == null) return '—';
  const hour = Math.floor(value);
  const minutes = Math.round((value - hour) * 60);
  return `${String(hour).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
};

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
        <div>
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

export default function DigitalEngagementPage() {
  const apiClient = getApiClient();
  const [anneeMois, setAnneeMois] = useState<number | null>(null);
  const [region, setRegion] = useState('');
  const [statut, setStatut] = useState('');

  const filtersQuery = useQuery<DigitalEngagementFiltersResponse>({
    queryKey: ['digital-engagement', 'filters'],
    queryFn: () => apiClient.request(digitalEngagementApi.filters()),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (anneeMois === null && (filtersQuery.data?.months?.length ?? 0) > 0) {
      setAnneeMois(filtersQuery.data!.months[0]);
    }
  }, [anneeMois, filtersQuery.data?.months]);

  const dashboardQuery = useQuery<DigitalEngagementDashboardResponse>({
    queryKey: ['digital-engagement', 'dashboard', anneeMois, region, statut],
    queryFn: () => apiClient.request(
      digitalEngagementApi.dashboard({
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
    setAnneeMois(filtersQuery.data?.months?.[0] ?? null);
    setRegion('');
    setStatut('');
  };

  return (
    <div className="min-h-screen bg-gray-50 p-3 pt-16 sm:p-4 sm:pt-16 lg:p-6 lg:pt-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-600">
            <Smartphone className="h-4 w-4" />
            Outils data
          </div>
          <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Engagement digital</h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600">
            Mesurez la fréquence mensuelle de connexion à l'application et le créneau de connexion dominant.
          </p>
        </div>

        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-[1fr_1.2fr_1fr_auto] lg:items-end">
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
            <Button variant="outline" onClick={resetFilters} className="w-full lg:w-auto">
              <RefreshCcw className="mr-2 h-4 w-4" />Réinitialiser
            </Button>
          </div>
        </div>

        {(filtersQuery.isLoading || (dashboardQuery.isLoading && !dashboardQuery.data)) && (
          <div className="flex min-h-[45vh] items-center justify-center"><LoadingSpinner size="lg" /></div>
        )}

        {(filtersQuery.error || dashboardQuery.error) && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Impossible de charger le tableau de bord d'engagement digital.
          </div>
        )}

        {dashboardQuery.data && summary && (
          <>
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
              <KpiCard title="Clients scorés" value={formatCount(summary.scored_clients)} subtitle="Actifs et inactifs" icon={<Users className="h-4 w-4" />} />
              <KpiCard title="Engagement élevé" value={formatCount(summary.high_clients)} subtitle={formatPercent(summary.high_rate)} icon={<TrendingUp className="h-4 w-4" />} />
              <KpiCard title="Médiane" value={summary.median_daily_connections.toFixed(2)} subtitle="Connexions / jour" icon={<Activity className="h-4 w-4" />} />
              <KpiCard title="Moyenne" value={summary.avg_daily_connections.toFixed(2)} subtitle="Connexions / jour" icon={<Smartphone className="h-4 w-4" />} />
              <KpiCard title="Heure moyenne" value={formatHour(summary.avg_weighted_hour)} subtitle="Heure pondérée" icon={<Clock3 className="h-4 w-4" />} />
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Répartition de l'engagement</h2>
                <p className="mb-4 text-xs text-gray-500">Faible &lt; médiane, Modéré entre x1 et x2, Élevé &gt; x2.</p>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dashboardQuery.data.engagement_distribution.map((item) => ({ ...item }))}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatCount(Number(value))} />
                      <Bar dataKey="clients" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Créneaux de connexion</h2>
                <p className="mb-4 text-xs text-gray-500">Matin 05h-12h, Après-midi 12h-18h, Soir 18h-05h.</p>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dashboardQuery.data.creneau_distribution.map((item) => ({ ...item }))}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatCount(Number(value))} />
                      <Bar dataKey="clients" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 p-4">
                <h2 className="text-base font-semibold text-gray-900">Engagement par région</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th className="px-4 py-3">Région</th>
                      <th className="px-4 py-3">Clients</th>
                      <th className="px-4 py-3">Élevé</th>
                      <th className="px-4 py-3">Taux élevé</th>
                      <th className="px-4 py-3">Connexions/jour</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {dashboardQuery.data.regions.map((item) => (
                      <tr key={item.region}>
                        <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">{item.region}</td>
                        <td className="px-4 py-3 text-gray-600">{formatCount(item.clients)}</td>
                        <td className="px-4 py-3 text-gray-600">{formatCount(item.high_clients)}</td>
                        <td className="px-4 py-3 text-gray-600">{formatPercent(item.clients ? item.high_clients / item.clients * 100 : 0)}</td>
                        <td className="px-4 py-3 text-gray-600">{Number(item.avg_daily_connections || 0).toFixed(2)}</td>
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
