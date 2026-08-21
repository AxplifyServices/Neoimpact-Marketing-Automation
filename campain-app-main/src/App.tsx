import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import LoadingSpinner from './components/LoadingSpinner';
import { routeLoaders } from './lib/route-preload';

const CampagnesPage = lazy(routeLoaders.campagnes);
const ModelesPage = lazy(routeLoaders.modeles);
const CreateModelePage = lazy(routeLoaders.createModele);
const ViewModelePage = lazy(routeLoaders.viewModele);
const CiblesPage = lazy(routeLoaders.cibles);
const CreateCiblePage = lazy(routeLoaders.createCible);
const ViewCiblePage = lazy(routeLoaders.viewCible);
const ClientsPage = lazy(routeLoaders.clients);
const CreateClientPage = lazy(routeLoaders.createClient);
const ViewClientPage = lazy(routeLoaders.viewClient);
const CRCPage = lazy(routeLoaders.crc);
const HistoriquePage = lazy(routeLoaders.historique);
const DashboardPage = lazy(routeLoaders.dashboard);

function RouteFallback() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center" role="status" aria-label="Chargement de la page">
      <LoadingSpinner size="lg" />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-x-hidden overflow-y-auto lg:ml-0">
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<Navigate to="/campagnes" replace />} />
              <Route path="/campagnes" element={<CampagnesPage />} />
              <Route path="/modeles" element={<ModelesPage />} />
              <Route path="/modeles/create" element={<CreateModelePage />} />
              <Route path="/modeles/:id/edit" element={<CreateModelePage />} />
              <Route path="/modeles/:id/view" element={<ViewModelePage />} />
              <Route path="/cibles" element={<CiblesPage />} />
              <Route path="/cibles/create" element={<CreateCiblePage />} />
              <Route path="/cibles/:id/edit" element={<CreateCiblePage />} />
              <Route path="/cibles/:id/view" element={<ViewCiblePage />} />
              <Route path="/clients" element={<ClientsPage />} />
              <Route path="/clients/create" element={<CreateClientPage />} />
              <Route path="/clients/:id/edit" element={<CreateClientPage />} />
              <Route path="/clients/:id/view" element={<ViewClientPage />} />
              <Route path="/crc" element={<CRCPage />} />
              <Route path="/historique" element={<HistoriquePage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/terrain" element={<Navigate to="/campagnes" replace />} />
              <Route path="/support" element={<Navigate to="/campagnes" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
