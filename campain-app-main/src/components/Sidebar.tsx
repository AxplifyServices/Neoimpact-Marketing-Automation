import {
  AlertTriangle,
  BarChart3,
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  History,
  LayoutDashboard,
  Megaphone,
  Menu,
  Phone,
  RadioTower,
  Target,
  Users,
  Smartphone,
  X,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { preloadRoute } from '@/lib/route-preload';

interface NavItem {
  icon: React.ReactNode;
  label: string;
  path: string;
  primary?: boolean;
}

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isDataToolsOpen, setIsDataToolsOpen] = useState(location.pathname.startsWith('/outils-data'));

  useEffect(() => {
    if (location.pathname.startsWith('/outils-data')) setIsDataToolsOpen(true);
  }, [location.pathname]);

  const navItems: NavItem[] = [
    { icon: <Megaphone size={16} />, label: 'Campagnes', path: '/campagnes', primary: true },
    { icon: <FileText size={16} />, label: 'Modèles', path: '/modeles' },
    { icon: <Target size={16} />, label: 'Cibles', path: '/cibles' },
    { icon: <Users size={16} />, label: 'Clients', path: '/clients' },
    { icon: <Phone size={16} />, label: 'CRC', path: '/crc' },
    { icon: <History size={16} />, label: 'Historique', path: '/historique' },
    { icon: <LayoutDashboard size={16} />, label: 'Dashboard', path: '/dashboard' },
  ];

  const handleNavigation = (path: string) => {
    navigate(path);
    setIsMobileMenuOpen(false);
  };

  const segmentationPath = '/outils-data/segmentation';
  const attritionPath = '/outils-data/attrition';
  const digitalEngagementPath = '/outils-data/engagement-digital';
  const bestChannelPath = '/outils-data/best-channel';
  const segmentationActive = location.pathname.startsWith(segmentationPath);
  const attritionActive = location.pathname.startsWith(attritionPath);
  const digitalEngagementActive = location.pathname.startsWith(digitalEngagementPath);
  const bestChannelActive = location.pathname.startsWith(bestChannelPath);
  const dataToolsActive = location.pathname.startsWith('/outils-data');

  return (
    <>
      <button
        type="button"
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        className="fixed left-4 top-4 z-50 rounded-xl bg-slate-900 p-2 text-white shadow-lg transition-colors hover:bg-slate-800 lg:hidden"
        aria-label={isMobileMenuOpen ? 'Fermer le menu' : 'Ouvrir le menu'}
      >
        {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-30 bg-black bg-opacity-50 lg:hidden" onClick={() => setIsMobileMenuOpen(false)} />
      )}

      <div className={`fixed inset-y-0 left-0 z-40 flex h-screen w-64 flex-col border-r border-gray-200 bg-white transform transition-transform duration-300 ease-in-out lg:static ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <div className="px-4 pb-4 pt-6">
          <h1 className="mb-1.5 text-2xl font-light">Campaign<span className="font-medium text-blue-600">Hub</span></h1>
          <p className="text-xs text-gray-500">Manage with ease</p>
        </div>

        <nav className="flex-1 overflow-y-auto px-4 pb-4">
          <div className="space-y-2">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <button
                  key={item.path}
                  type="button"
                  onClick={() => handleNavigation(item.path)}
                  onMouseEnter={() => preloadRoute(item.path)}
                  onFocus={() => preloadRoute(item.path)}
                  onPointerDown={() => preloadRoute(item.path)}
                  className={`flex w-full items-center justify-between rounded-xl px-3 py-2 transition-all duration-200 ${isActive ? 'bg-slate-900 text-white shadow-lg hover:bg-slate-800' : 'text-gray-700 hover:bg-gray-100'}`}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-4 w-4 items-center justify-center">{item.icon}</div>
                    <span className="text-sm font-medium">{item.label}</span>
                  </div>
                  {isActive && <ChevronRight size={16} />}
                </button>
              );
            })}

            <div className="pt-1">
              <button
                type="button"
                onClick={() => setIsDataToolsOpen((open) => !open)}
                className={`flex w-full items-center justify-between rounded-xl px-3 py-2 transition-all duration-200 ${dataToolsActive ? 'bg-slate-100 text-slate-900' : 'text-gray-700 hover:bg-gray-100'}`}
                aria-expanded={isDataToolsOpen}
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-4 w-4 items-center justify-center"><Database size={16} /></div>
                  <span className="text-sm font-medium">Outils data</span>
                </div>
                <ChevronDown size={16} className={`transition-transform ${isDataToolsOpen ? 'rotate-180' : ''}`} />
              </button>

              {isDataToolsOpen && (
                <div className="ml-4 mt-1 border-l border-gray-200 pl-3">
                  <button
                    type="button"
                    onClick={() => handleNavigation(segmentationPath)}
                    onMouseEnter={() => preloadRoute(segmentationPath)}
                    onFocus={() => preloadRoute(segmentationPath)}
                    onPointerDown={() => preloadRoute(segmentationPath)}
                    className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${segmentationActive ? 'bg-slate-900 text-white' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'}`}
                  >
                    <div className="flex items-center gap-2.5"><BarChart3 size={15} /><span className="font-medium">Segmentation</span></div>
                    {segmentationActive && <ChevronRight size={14} />}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleNavigation(attritionPath)}
                    onMouseEnter={() => preloadRoute(attritionPath)}
                    onFocus={() => preloadRoute(attritionPath)}
                    onPointerDown={() => preloadRoute(attritionPath)}
                    className={`mt-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${attritionActive ? 'bg-slate-900 text-white' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'}`}
                  >
                    <div className="flex items-center gap-2.5"><AlertTriangle size={15} /><span className="font-medium">Attrition</span></div>
                    {attritionActive && <ChevronRight size={14} />}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleNavigation(digitalEngagementPath)}
                    onMouseEnter={() => preloadRoute(digitalEngagementPath)}
                    onFocus={() => preloadRoute(digitalEngagementPath)}
                    onPointerDown={() => preloadRoute(digitalEngagementPath)}
                    className={`mt-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${digitalEngagementActive ? 'bg-slate-900 text-white' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'}`}
                  >
                    <div className="flex items-center gap-2.5"><Smartphone size={15} /><span className="font-medium">Engagement digital</span></div>
                    {digitalEngagementActive && <ChevronRight size={14} />}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleNavigation(bestChannelPath)}
                    onMouseEnter={() => preloadRoute(bestChannelPath)}
                    onFocus={() => preloadRoute(bestChannelPath)}
                    onPointerDown={() => preloadRoute(bestChannelPath)}
                    className={`mt-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${bestChannelActive ? 'bg-slate-900 text-white' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'}`}
                  >
                    <div className="flex items-center gap-2.5"><RadioTower size={15} /><span className="font-medium">Best canal</span></div>
                    {bestChannelActive && <ChevronRight size={14} />}
                  </button>
                </div>
              )}
            </div>
          </div>
        </nav>
      </div>
    </>
  );
}
