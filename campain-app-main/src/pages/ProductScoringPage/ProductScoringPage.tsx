import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BadgeDollarSign,
  CreditCard,
  PiggyBank,
  RefreshCcw,
  ShoppingBag,
  Target,
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
import { productScoringApi } from '@/lib/api/definitions/product-scoring.api';
import type {
  ProductScoringDashboardResponse,
  ProductScoringFiltersResponse,
} from '@/types/product-scoring.types';

const formatCount = (value?: number | null) => Number(value ?? 0).toLocaleString('fr-FR');
const formatPct = (value?: number | null) => `${(Number(value ?? 0) * 100).toFixed(1)} %`;
const formatRate = (value?: number | null) => `${Number(value ?? 0).toFixed(1)} %`;
const formatAuc = (value?: number | null) => value == null ? '—' : Number(value).toFixed(3);
const formatMonth = (value: number) => {
  const year = Math.floor(value / 100);
  const month = value % 100;
  return new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric' }).format(new Date(year, month - 1, 1));
};

const creditSegmentLabel = (value?: string | null) => ({
  never: 'Jamais équipé',
  finished: 'Crédit terminé',
  active: 'Crédit en cours / recharge',
}[value ?? ''] ?? value ?? 'Non renseigné');

const modelLabel = (value: string) => ({
  card_silver: 'Carte Silver',
  card_titanium: 'Carte Titanium',
  card_platinium: 'Carte Platinium',
  card_infinite: 'Carte Infinite',
  epargne: 'Épargne',
  conso_never: 'Conso — jamais équipé',
  conso_finished: 'Conso — crédit terminé',
  conso_active: 'Conso — recharge',
  immo_never: 'Immo — jamais équipé',
  immo_finished: 'Immo — crédit terminé',
  immo_active: 'Immo — recharge',
}[value] ?? value);

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

export default function ProductScoringPage() {
  const apiClient = getApiClient();
  const [anneeMois, setAnneeMois] = useState<number | null>(null);
  const [region, setRegion] = useState('');
  const [statut, setStatut] = useState('');

  const filtersQuery = useQuery<ProductScoringFiltersResponse>({
    queryKey: ['product-scoring', 'filters'],
    queryFn: () => apiClient.request(productScoringApi.filters()),
    staleTime: 5 * 60 * 1000,
    refetchInterval: anneeMois === null ? 30_000 : false,
  });

  useEffect(() => {
    if (anneeMois === null && filtersQuery.data?.default_annee_mois) {
      setAnneeMois(filtersQuery.data.default_annee_mois);
    }
  }, [anneeMois, filtersQuery.data?.default_annee_mois]);

  const dashboardQuery = useQuery<ProductScoringDashboardResponse>({
    queryKey: ['product-scoring', 'dashboard', anneeMois, region, statut],
    queryFn: () => apiClient.request(productScoringApi.dashboard({
      annee_mois: anneeMois ?? undefined,
      region: region || undefined,
      statut_client: statut || undefined,
    })),
    enabled: anneeMois !== null,
    staleTime: 60 * 1000,
  });

  const summary = dashboardQuery.data?.summary;
  const appetiteData = useMemo(() => summary ? [
    { product: 'Carte', score: summary.avg_card },
    { product: 'Crédit conso', score: summary.avg_conso },
    { product: 'Crédit immo', score: summary.avg_immo },
    { product: 'Épargne', score: summary.avg_epargne },
  ] : [], [summary]);

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
              <ShoppingBag className="h-4 w-4" />
              Outils data
            </div>
            <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Appétences produits</h1>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Scores mensuels Carte, Crédit conso, Crédit immo et Épargne, avec recommandation du Next Best Product pour chaque client.
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
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-[1fr_1.2fr_1fr_auto] xl:items-end">
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
            <Button variant="outline" onClick={resetFilters} className="w-full xl:w-auto"><RefreshCcw className="mr-2 h-4 w-4" />Réinitialiser</Button>
          </div>
        </div>

        {filtersQuery.isLoading && <div className="flex min-h-[45vh] items-center justify-center"><LoadingSpinner size="lg" /></div>}
        {!filtersQuery.isLoading && (filtersQuery.data?.months?.length ?? 0) === 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">Aucun scoring produit n'est encore disponible.</div>
        )}
        {(filtersQuery.error || dashboardQuery.error) && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">Impossible de charger le tableau de bord des appétences produits.</div>
        )}
        {dashboardQuery.isLoading && !dashboardQuery.data && <div className="flex min-h-[45vh] items-center justify-center"><LoadingSpinner size="lg" /></div>}

        {dashboardQuery.data && summary && (
          <>
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
              <KpiCard title="Clients scorés" value={formatCount(summary.scored_clients)} subtitle="Actifs et inactifs" icon={<Users className="h-4 w-4" />} />
              <KpiCard title="Appétence Carte" value={formatPct(summary.avg_card)} subtitle="Moyenne des éligibles" icon={<CreditCard className="h-4 w-4" />} />
              <KpiCard title="Appétence Conso" value={formatPct(summary.avg_conso)} subtitle="3 modèles d'équipement" icon={<BadgeDollarSign className="h-4 w-4" />} />
              <KpiCard title="Appétence Immo" value={formatPct(summary.avg_immo)} subtitle="3 modèles d'équipement" icon={<Target className="h-4 w-4" />} />
              <KpiCard title="Appétence Épargne" value={formatPct(summary.avg_epargne)} subtitle="Clients non équipés" icon={<PiggyBank className="h-4 w-4" />} />
              <KpiCard title="Score NBP moyen" value={formatPct(summary.avg_nbp_score)} subtitle="Meilleur score disponible" icon={<ShoppingBag className="h-4 w-4" />} />
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Next Best Product</h2>
                <p className="mb-4 text-xs text-gray-500">Produit présentant le score d'appétence éligible le plus élevé.</p>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dashboardQuery.data.next_best_product}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="product" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatCount(Number(value))} />
                      <Bar dataKey="clients" name="Clients" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Appétence moyenne par famille</h2>
                <p className="mb-4 text-xs text-gray-500">Probabilité moyenne calculée par les modèles mensuels.</p>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={appetiteData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="product" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(Number(v) * 100)}%`} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatPct(Number(value))} />
                      <Bar dataKey="score" name="Score moyen" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Carte recommandée</h2>
                <p className="mb-4 text-xs text-gray-500">La carte détenue et les gammes inférieures sont exclues du scoring final.</p>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dashboardQuery.data.card_recommendations}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="card" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatCount(Number(value))} />
                      <Bar dataKey="clients" name="Clients" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-base font-semibold text-gray-900">Retour des campagnes</h2>
                <p className="mb-4 text-xs text-gray-500">Résultats rattachés au score qui existait lors du lancement de la campagne.</p>
                <div className="grid grid-cols-2 gap-3">
                  <KpiCard title="Affectations" value={formatCount(dashboardQuery.data.feedback.assignments)} subtitle="Objectifs produits" icon={<Target className="h-4 w-4" />} />
                  <KpiCard title="Contacts réels" value={formatCount(dashboardQuery.data.feedback.contacted)} subtitle={`${formatCount(dashboardQuery.data.feedback.resolved)} objectifs évalués`} icon={<Target className="h-4 w-4" />} />
                  <KpiCard title="Conversions" value={formatCount(dashboardQuery.data.feedback.conversions)} subtitle={formatRate(dashboardQuery.data.feedback.conversion_rate)} icon={<BadgeDollarSign className="h-4 w-4" />} />
                  <KpiCard title="Appétents contactés" value={formatCount(dashboardQuery.data.feedback.appetent_assignments)} subtitle="Score ≥ 50 % au lancement" icon={<Users className="h-4 w-4" />} />
                </div>
              </div>
            </div>

            <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
              {(['conso', 'immo'] as const).map((kind) => (
                <div key={kind} className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                  <div className="border-b border-gray-100 p-4">
                    <h2 className="text-base font-semibold text-gray-900">Crédit {kind === 'conso' ? 'conso' : 'immo'} — populations scorées</h2>
                    <p className="text-xs text-gray-500">Chaque client passe dans un seul modèle selon son état d'équipement.</p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500"><tr><th className="px-4 py-3">Population</th><th className="px-4 py-3">Clients</th><th className="px-4 py-3">Score moyen</th></tr></thead>
                      <tbody className="divide-y divide-gray-100">
                        {dashboardQuery.data.credit_segments[kind].map((row) => (
                          <tr key={`${kind}-${row.segment}`}><td className="px-4 py-3 font-medium text-gray-900">{creditSegmentLabel(row.segment)}</td><td className="px-4 py-3 text-gray-700">{formatCount(row.clients)}</td><td className="px-4 py-3 text-gray-700">{formatPct(row.avg_score)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>

            <div className="mb-6 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 p-4">
                <h2 className="text-base font-semibold text-gray-900">Performance des modèles</h2>
                <p className="text-xs text-gray-500">Un modèle par carte, un modèle Épargne et trois modèles par type de crédit.</p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500"><tr><th className="px-4 py-3">Modèle</th><th className="px-4 py-3">AUC validation</th><th className="px-4 py-3">Lignes train</th><th className="px-4 py-3">Positifs</th></tr></thead>
                  <tbody className="divide-y divide-gray-100">
                    {dashboardQuery.data.models.map((model) => (
                      <tr key={model.model_code}><td className="px-4 py-3 font-medium text-gray-900">{modelLabel(model.model_code)}</td><td className="px-4 py-3 text-gray-700">{formatAuc(model.validation_auc)}</td><td className="px-4 py-3 text-gray-700">{formatCount(model.training_rows)}</td><td className="px-4 py-3 text-gray-700">{formatCount(model.positive_rows)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 p-4">
                <h2 className="text-base font-semibold text-gray-900">Appétences par région</h2>
                <p className="text-xs text-gray-500">Scores moyens et Next Best Product dominant.</p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500"><tr><th className="px-4 py-3">Région</th><th className="px-4 py-3">Clients</th><th className="px-4 py-3">NBP dominant</th><th className="px-4 py-3">Carte</th><th className="px-4 py-3">Conso</th><th className="px-4 py-3">Immo</th><th className="px-4 py-3">Épargne</th></tr></thead>
                  <tbody className="divide-y divide-gray-100">
                    {dashboardQuery.data.regions.map((row) => (
                      <tr key={row.region}><td className="px-4 py-3 font-medium text-gray-900">{row.region}</td><td className="px-4 py-3 text-gray-700">{formatCount(row.clients)}</td><td className="px-4 py-3 text-gray-700">{row.dominant_product}</td><td className="px-4 py-3 text-gray-700">{formatPct(row.avg_card)}</td><td className="px-4 py-3 text-gray-700">{formatPct(row.avg_conso)}</td><td className="px-4 py-3 text-gray-700">{formatPct(row.avg_immo)}</td><td className="px-4 py-3 text-gray-700">{formatPct(row.avg_epargne)}</td></tr>
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
