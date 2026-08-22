import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  resetKey: string;
}

interface State {
  error: Error | null;
}

const RELOAD_GUARD_KEY = 'campaignhub:last-chunk-reload';

function isChunkLoadError(error: Error): boolean {
  const message = `${error.name || ''} ${error.message || ''}`.toLowerCase();
  return (
    message.includes('failed to fetch dynamically imported module') ||
    message.includes('importing a module script failed') ||
    message.includes('chunkloaderror') ||
    message.includes('loading chunk') ||
    message.includes('dynamically imported module')
  );
}

export default class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[RouteErrorBoundary] Route render failed', error, info);

    // Un déploiement remplace les fichiers hashés. Un onglet ouvert avant le
    // déploiement peut encore demander un ancien chunk lazy qui n'existe plus.
    // On recharge automatiquement une seule fois pour récupérer le nouvel index.
    if (isChunkLoadError(error)) {
      try {
        const lastReload = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) || '0');
        if (!Number.isFinite(lastReload) || Date.now() - lastReload > 30_000) {
          sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()));
          window.location.reload();
        }
      } catch {
        // Le panneau de récupération ci-dessous reste disponible.
      }
    }
  }

  componentDidUpdate(prevProps: Props) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  private retry = () => {
    this.setState({ error: null });
  };

  private hardReload = () => {
    try {
      sessionStorage.removeItem(RELOAD_GUARD_KEY);
    } catch {
      // no-op
    }
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="min-h-[60vh] bg-gray-50 p-4 sm:p-6 lg:p-8 pt-20 lg:pt-8">
        <div className="mx-auto max-w-2xl rounded-2xl border border-amber-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Impossible d'afficher cette page</h2>
          <p className="mt-2 text-sm text-gray-600">
            La page a rencontré une erreur de chargement. Vos données n'ont pas été modifiées.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={this.retry}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
            >
              Réessayer
            </button>
            <button
              type="button"
              onClick={this.hardReload}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Recharger l'application
            </button>
          </div>
        </div>
      </div>
    );
  }
}
