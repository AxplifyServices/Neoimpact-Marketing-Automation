import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import CampagnesPage from './pages/CampagnesPage';
import ModelesPage from './pages/ModelesPage';
import CreateModelePage from './pages/CreateModelePage';
import ViewModelePage from './pages/ViewModelePage';
import CiblesPage from './pages/CiblesPage';
import CreateCiblePage from './pages/CreateCiblePage';
import ViewCiblePage from './pages/ViewCiblePage';
import ClientsPage from './pages/ClientsPage';
import CreateClientPage from './pages/CreateClientPage';
import ViewClientPage from './pages/ViewClientPage';
import CRCPage from './pages/CRCPage';
import HistoriquePage from './pages/HistoriquePage';
import DashboardPage from './pages/DashboardPage';
import ContactSupportPage from './pages/ContactSupportPage';

function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-x-hidden overflow-y-auto lg:ml-0">
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
            <Route path="/support" element={<ContactSupportPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App
