import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  CalendarDays,
  RefreshCcw,
  Target,
  TrendingDown,
  Users,
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
import { attritionApi } from '@/lib/api/definitions/attrition.api';
import type { AttritionDashboardResponse, AttritionFiltersResponse } from '@/types/attrition.types';

const formatMonth = (value: number) => {
  const raw = String(value);
  return raw.length === 6 ? `${raw.slice(4, 6)}/${raw.slice(0, 4)}` : raw;
};

const formatCount = (value: number) => new Intl.NumberFormat('fr-FR').format(value || 0);
const formatPercent = (value: number) => `${(value || 0).toFixed(1)} %`;
const formatScore = (value: number) => `${((value || 0) * 100).toFixed(1)} %`;
const formatVariation = (value: number) => `${value >= 0 ? '+' : ''}${((value || 0) * 100).toFixed(1)} %`;

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
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700">{icon}</div>
      </div>
    </div>
  );
}

export default function AttritionPage() {
  const apiClient = getApiClient();
  const [anneeMois, setAnneeMois] = useState<number | null>(null);
  const [region, setRegion] = useState('');
  const [statut, setStatut] = useState('');

  const filtersQuery = useQuery<AttritionFiltersResponse>({
    queryKey: ['attrition', 'filters'],
    queryFn: () => apiClient.request(attritionApi.filters()),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (anneeMois === null && filtersQuery.data?.default_annee_mois) {
      setAnneeMois(filtersQuery.data.default_annee_mois);
    }
  }, [anneeMois, filtersQuery.data?.default_annee_mois]);

  const dashboardQuery = useQuery<AttritionDashboardResponse>({
    queryKey: ['attrition', 'dashboard', anneeMois, region, statut],
    queryFn: () => apiClient.request(
      attritionApi.dashboard({
        annee_mois: anneeMois!,
        ...(region ? { region } : {}),
        ...(statut ? { statut } : {}),
      })
    ),
    enabled: anneeMois !== null,
    staleTime: 60 * 1000,
  });

  const kpis = dashboardQuery.data?.kpis;
  const variationData = useMemo(() => {
    const source = dashboardQuery.data?.variations_risque;
    if (!source) return [];
    return source.horizons.map((horizon, index) => ({
      horizon,
      avoirs: source.avoirs[index] ?? 0,
      credits: source.flux_crediteurs[index] ?? 0,
      debits: source.flux_debiteurs[index] ?? 0,
    }));
  }, [dashboardQuery.data?.variations_risque]);

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
              <BrainCircuit className="h-4 w-4" />
              Outils data
            </div>
            <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Attrition</h1>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Suivez le score XGBoost mensuel et les décotes d'avoirs, de flux créditeurs et de flux débiteurs des clients à risque.
            </p>
          </div>
          {kpis?.date_scoring && (
            <div className="text-xs text-gray-500 sm:text-right">
              Dernier scoring<br />
              <span className="font-medium text-gray-800">{kpis.date_scoring}</span>
            </div>
          )}
        </div>

        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-[1fr_1.2fr_1fr_auto] lg:items-end">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-600">Mois / année</label>
              <select value={anneeMois ?? ''} onChange={(e) => setAnneeMois(Number(e.target.value))} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
                {(filtersQuery.data?.annee_mois ?? []).map((month) => <option key={month} value={month}>{formatMonth(month)}</option>)}
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
                {(filtersQuery.data?.statuts ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <Button variant="outline" onClick={resetFilters} className="w-full lg:w-auto"><RefreshCcw className="mr-2 h-4 w-4" />Réinitialiser</Button>
          </div>
        </div>

        {(filtersQuery.isLoading || (dashboardQuery.isLoading && !dashboardQuery.data)) && (
          <div className="flex min-h-[45vh] items-center justify-center"><LoadingSpinner size="lg" /></div>
        )}

        {(filtersQuery.error || dashboardQuery.error) && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">Impossible de charger le tableau de bord d'attrition.</div>
        )}

        {dashboardQuery.data && kpis && (
          <>
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
              <KpiCard title="Clients scorés" value={formatCount(kpis.clients_scores)} subtitle="Actifs et inactifs" icon={<Users className="h-4 w-4" />} />
              <KpiCard title="Clients à risque" value={formatCount(kpis.clients_risque)} subtitle="Flag Risque attrition = Oui" icon={<AlertTriangle className="h-4 w-4" />} />
              <KpiCard title="Taux à risque" value={formatPercent(kpis.taux_risque)} subtitle="Part de la population scorée" icon={<Target className="h-4 w-4" />} />
              <KpiCard title="Score moyen" value={formatScore(kpis.score_moyen)} subtitle="Probabilité moyenne" icon={<Activity className="h-4 w-4" />} />
              <KpiCard title="Score moyen risque" value={formatScore(kpis.score_moyen_risque)} subtitle="Clients flaggés uniquement" icon={<TrendingDown className="h-4 w-4" />} />
              <KpiCard title="Seuil" value={formatScore(kpis.seuil_risque)} subtitle="Seuil de flag du batch" icon={<CalendarDays className="h-4 w-4" />} />
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Distribution des scores</h2>
                <p className="mb-4 text-xs text-gray-500">Répartition de la probabilité de rupture calculée par le modèle.</p>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dashboardQuery.data.score_bands.map((item) => ({ ...item }))}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="tranche" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatCount(Number(value))} />
                      <Bar dataKey="clients" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Décotes moyennes des clients à risque</h2>
                <p className="mb-4 text-xs text-gray-500">Variation relative : -0,20 = baisse de 20 %, +0,20 = hausse de 20 %.</p>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={variationData.map((item) => ({ ...item }))}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="horizon" tick={{ fontSize: 11 }} />
                      <YAxis tickFormatter={(value) => `${Math.round(Number(value) * 100)}%`} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatVariation(Number(value))} />
                      <Legend />
                      <Bar dataKey="avoirs" name="Avoirs" />
                      <Bar dataKey="credits" name="Flux créditeurs" />
                      <Bar dataKey="debits" name="Flux débiteurs" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-[1.4fr_1fr]">
              <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                <div className="border-b border-gray-100 p-4">
                  <h2 className="text-base font-semibold text-gray-900">Risque par région</h2>
                  <p className="text-xs text-gray-500">Population scorée et taux de clients flaggés.</p>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                      <tr><th className="px-4 py-3">Région</th><th className="px-4 py-3">Scorés</th><th className="px-4 py-3">À risque</th><th className="px-4 py-3">Taux</th><th className="px-4 py-3">Score moyen</th></tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {dashboardQuery.data.regions.map((item) => (
                        <tr key={item.region}>
                          <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">{item.region}</td>
                          <td className="px-4 py-3 text-gray-600">{formatCount(item.clients_scores)}</td>
                          <td className="px-4 py-3 text-gray-600">{formatCount(item.clients_risque)}</td>
                          <td className="px-4 py-3 text-gray-600">{formatPercent(item.taux_risque)}</td>
                          <td className="px-4 py-3 text-gray-600">{formatScore(item.score_moyen)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Modèle</h2>
                <div className="mt-4 space-y-3 text-sm">
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Statut</span><span className="font-medium text-gray-900">{dashboardQuery.data.model.exists ? 'Disponible' : 'Absent'}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Type</span><span className="font-medium text-gray-900">XGBoost</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Lignes historiques</span><span className="font-medium text-gray-900">{formatCount(dashboardQuery.data.training.rows)}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Ruptures observées</span><span className="font-medium text-gray-900">{formatCount(dashboardQuery.data.training.attritions_observees)}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">AUC validation</span><span className="font-medium text-gray-900">{dashboardQuery.data.model.validation_auc == null ? '—' : dashboardQuery.data.model.validation_auc.toFixed(3)}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Precision</span><span className="font-medium text-gray-900">{dashboardQuery.data.model.validation_precision == null ? '—' : formatScore(dashboardQuery.data.model.validation_precision)}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-gray-500">Recall</span><span className="font-medium text-gray-900">{dashboardQuery.data.model.validation_recall == null ? '—' : formatScore(dashboardQuery.data.model.validation_recall)}</span></div>
                  <div className="border-t border-gray-100 pt-3 text-xs text-gray-500">Si aucun modèle n'existe au déclenchement du batch, le worker entraîne automatiquement un nouveau modèle puis le sauvegarde avant scoring.</div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
