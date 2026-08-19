import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import LoadingSpinner from './components/LoadingSpinner';

const CampagnesPage = lazy(() => import('./pages/CampagnesPage'));
const ModelesPage = lazy(() => import('./pages/ModelesPage'));
const CreateModelePage = lazy(() => import('./pages/CreateModelePage'));
const ViewModelePage = lazy(() => import('./pages/ViewModelePage'));
const CiblesPage = lazy(() => import('./pages/CiblesPage'));
const CreateCiblePage = lazy(() => import('./pages/CreateCiblePage'));
const ViewCiblePage = lazy(() => import('./pages/ViewCiblePage'));
const ClientsPage = lazy(() => import('./pages/ClientsPage'));
const CreateClientPage = lazy(() => import('./pages/CreateClientPage'));
const ViewClientPage = lazy(() => import('./pages/ViewClientPage'));
const CRCPage = lazy(() => import('./pages/CRCPage'));
const TerrainPage = lazy(() => import('./pages/TerrainPage'));
const HistoriquePage = lazy(() => import('./pages/HistoriquePage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const ContactSupportPage = lazy(() => import('./pages/ContactSupportPage'));

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
              <Route path="/terrain" element={<TerrainPage />} />
              <Route path="/historique" element={<HistoriquePage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/support" element={<ContactSupportPage />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
