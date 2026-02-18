import { Megaphone, Plus, Phone, History, LayoutDashboard, ChevronRight, Menu, X, FileText, Target, Users } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useState } from 'react';

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

  return (
    <>
      {/* Mobile Menu Button */}
      <button
        type="button"
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-slate-900 text-white rounded-xl shadow-lg hover:bg-slate-800 transition-colors"
      >
        {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      {/* Mobile Overlay */}
      {isMobileMenuOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black bg-opacity-50 z-30"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`
        fixed lg:static inset-y-0 left-0 z-40
        w-64 h-screen bg-white flex flex-col border-r border-gray-200
        transform transition-transform duration-300 ease-in-out
        ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
      {/* Header */}
      <div className="px-4 pt-6 pb-4">
        <h1 className="text-2xl font-light mb-1.5">
          Campaign<span className="text-blue-600 font-medium">Hub</span>
        </h1>
        <p className="text-gray-500 text-xs">Manage with ease</p>
      </div>

        {/* Navigation */}
        <nav className="px-4 flex-1">
          <div className="space-y-2">
            {navItems.map((item, index) => {
              const isActive = location.pathname === item.path;
              return (
                <button
                  key={index}
                  type="button"
                  onClick={() => handleNavigation(item.path)}
                  className={`
                    w-full flex items-center justify-between
                    px-3 py-2 rounded-xl
                    transition-all duration-200
                    ${
                      isActive
                        ? 'bg-slate-900 text-white hover:bg-slate-800 shadow-lg'
                        : 'text-gray-700 hover:bg-gray-100'
                    }
                  `}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 flex items-center justify-center">
                      {item.icon}
                    </div>
                    <span className="text-sm font-medium">{item.label}</span>
                  </div>
                  {isActive && <ChevronRight size={16} />}
                </button>
              );
            })}
          </div>
        </nav>

        {/* Help Section */}
        <div className="px-4 pb-6">
          <div className="bg-blue-50 rounded-xl p-3">
            <p className="text-gray-600 text-xs mb-2">Need help?</p>
            <button
              type="button"
              onClick={() => handleNavigation('/support')}
              className="text-blue-600 font-semibold text-xs flex items-center gap-2 hover:gap-3 transition-all"
            >
              Contact Support
              <span>→</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
