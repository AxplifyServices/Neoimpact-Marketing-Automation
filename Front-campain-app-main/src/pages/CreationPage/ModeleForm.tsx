import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

interface ModeleFormProps {
  onSubmit: () => void;
}

export default function ModeleForm({ onSubmit }: ModeleFormProps) {
  const [formData, setFormData] = useState({
    nom: '',
    type: 'APPEL_ALERT',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.nom.trim()) {
      newErrors.nom = 'Le nom du modèle est requis';
    }

    if (formData.nom.trim().length < 3) {
      newErrors.nom = 'Le nom du modèle doit contenir au moins 3 caractères';
    }

    if (!formData.type) {
      newErrors.type = 'Le type de modèle est requis';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validateForm()) {
      onSubmit();
      // Reset form
      setFormData({
        nom: '',
        type: 'APPEL_ALERT',
      });
      setErrors({});
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-2xl p-4 sm:p-6 lg:p-8 shadow-sm border border-gray-100">
      <h3 className="text-lg sm:text-xl font-bold text-gray-900 mb-4 sm:mb-6">Créer un modèle</h3>

      <p className="text-gray-600 text-sm sm:text-base mb-6 sm:mb-8">Configuration du modèle d'action pour vos campagnes</p>

      <div className="space-y-4 sm:space-y-6">
        {/* Nom du modèle */}
        <div>
          <label className="block text-xs sm:text-sm font-medium text-gray-700 mb-2">
            Nom du modèle <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={formData.nom}
            onChange={(e) => setFormData({ ...formData, nom: e.target.value })}
            placeholder="Entrez le nom du modèle"
            className={`w-full px-4 py-3 bg-gray-50 border ${
              errors.nom ? 'border-red-500' : 'border-gray-200'
            } rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent`}
          />
          {errors.nom && <p className="mt-1 text-sm text-red-500">{errors.nom}</p>}
        </div>

        {/* Type de modèle */}
        <div>
          <label className="block text-xs sm:text-sm font-medium text-gray-700 mb-2">
            Type de modèle <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <select
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
              className={`w-full px-4 py-3 bg-gray-50 border ${
                errors.type ? 'border-red-500' : 'border-gray-200'
              } rounded-xl text-gray-700 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-pink-500`}
            >
              <option value="APPEL_ALERT">APPEL_ALERT</option>
              <option value="SMS">SMS</option>
              <option value="EMAIL">EMAIL</option>
            </select>
            <ChevronDown className="w-5 h-5 absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
          </div>
          {errors.type && <p className="mt-1 text-sm text-red-500">{errors.type}</p>}
        </div>

        {/* Create Button */}
        <button
          type="submit"
          className="w-full py-4 bg-pink-600 hover:bg-pink-700 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2 cursor-pointer"
        >
          <span className="text-xl">+</span>
          Créer le modèle
        </button>
      </div>
    </form>
  );
}
