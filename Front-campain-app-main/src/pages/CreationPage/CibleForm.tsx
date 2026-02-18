import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

interface CibleFormProps {
  onSubmit: (data: any) => void;
}

export default function CibleForm({ onSubmit }: CibleFormProps) {
  const [formData, setFormData] = useState({
    nom: '',
    gender: '',
    ageRange: '',
    environment: '',
    statutClient: '',
    qualite: '',
    region: '',
    agence: '',
    environmentRef: '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [source, setSource] = useState('database');
  const isFileModeDisabled = true;

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.nom.trim()) {
      newErrors.nom = 'Le nom de la cible est requis';
    }

    if (!formData.gender) {
      newErrors.gender = 'Le genre est requis';
    }

    if (!formData.ageRange) {
      newErrors.ageRange = "La tranche d'âge est requise";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validateForm()) {
      // Prepare data for API (map to Cible type)
      const cibleData = {
        name: formData.nom,
        type: source === 'database' ? 'DB' : 'FILE',
        // Additional fields can be stored as metadata if needed
      };
      onSubmit(cibleData);
      // Reset form
      setFormData({
        nom: '',
        gender: '',
        ageRange: '',
        environment: '',
        statutClient: '',
        qualite: '',
        region: '',
        agence: '',
        environmentRef: '',
      });
      setErrors({});
      setSource('database');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-2xl p-4 sm:p-6 lg:p-8 shadow-sm border border-gray-100 mb-6 sm:mb-8">
      <h3 className="text-lg sm:text-xl font-bold text-gray-900 mb-4 sm:mb-6">Créer une cible</h3>

      <div className="space-y-4 sm:space-y-6">
        {/* Nom de la cible */}
        <div>
          <label className="block text-xs sm:text-sm font-medium text-gray-700 mb-2">
            Nom de la cible <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={formData.nom}
            onChange={(e) => setFormData({ ...formData, nom: e.target.value })}
            placeholder="Entrez le nom"
            className={`w-full px-4 py-3 bg-gray-50 border ${
              errors.nom ? 'border-red-500' : 'border-gray-200'
            } rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent`}
          />
          {errors.nom && <p className="mt-1 text-sm text-red-500">{errors.nom}</p>}
        </div>

        {/* Source */}
        <div>
          <label className="block text-xs sm:text-sm font-medium text-gray-700 mb-3">
            Source
          </label>
          <div className="flex flex-col sm:flex-row gap-4 sm:gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="source"
                value="database"
                checked={source === 'database'}
                onChange={(e) => setSource(e.target.value)}
                className="w-5 h-5 text-pink-600 focus:ring-pink-500"
              />
              <span className="text-gray-700">Depuis la base de données</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="source"
                value="file"
                checked={source === 'file'}
                onChange={(e) => setSource(e.target.value)}
                disabled={isFileModeDisabled}
                className={`w-5 h-5 text-pink-600 focus:ring-pink-500 ${isFileModeDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              />
              <span className={`text-gray-700 ${isFileModeDisabled ? 'opacity-50' : ''}`}>Depuis un fichier psd</span>
            </label>
          </div>
        </div>

        {/* Filtres Section */}
        <div>
          <h4 className="text-lg font-bold text-gray-900 mb-4">Filtres</h4>

          <div className="grid grid-cols-2 gap-4 mb-4">
            {/* First Row Dropdowns */}
            <div>
              <div className="relative">
                <select
                  value={formData.gender}
                  onChange={(e) => setFormData({ ...formData, gender: e.target.value })}
                  className={`w-full px-4 py-3 bg-gray-50 border ${
                    errors.gender ? 'border-red-500' : 'border-gray-200'
                  } rounded-xl text-gray-700 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-pink-500`}
                >
                  <option value="" disabled hidden>— choisi —</option>
                  <option value="homme">Homme</option>
                  <option value="femme">Femme</option>
                </select>
                <ChevronDown className="w-5 h-5 absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
              </div>
              {errors.gender && <p className="mt-1 text-sm text-red-500">{errors.gender}</p>}
            </div>
            <div>
              <div className="relative">
                <select
                  value={formData.ageRange}
                  onChange={(e) => setFormData({ ...formData, ageRange: e.target.value })}
                  className={`w-full px-4 py-3 bg-gray-50 border ${
                    errors.ageRange ? 'border-red-500' : 'border-gray-200'
                  } rounded-xl text-gray-700 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-pink-500`}
                >
                  <option value="" disabled hidden>— choisi —</option>
                  <option value="18-25">18-25</option>
                  <option value="26-35">26-35</option>
                  <option value="36-50">36-50</option>
                </select>
                <ChevronDown className="w-5 h-5 absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
              </div>
              {errors.ageRange && <p className="mt-1 text-sm text-red-500">{errors.ageRange}</p>}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-4">
            {/* Second Row Inputs */}
            <input
              type="text"
              value={formData.environment}
              onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
              placeholder="Environment"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
            <input
              type="text"
              value={formData.statutClient}
              onChange={(e) => setFormData({ ...formData, statutClient: e.target.value })}
              placeholder="Statut client"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4 mb-4">
            {/* Third Row Inputs */}
            <input
              type="text"
              value={formData.qualite}
              onChange={(e) => setFormData({ ...formData, qualite: e.target.value })}
              placeholder="Qualité"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
            <input
              type="text"
              value={formData.region}
              onChange={(e) => setFormData({ ...formData, region: e.target.value })}
              placeholder="Région"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Fourth Row Inputs */}
            <input
              type="text"
              value={formData.agence}
              onChange={(e) => setFormData({ ...formData, agence: e.target.value })}
              placeholder="Agence"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
            <input
              type="text"
              value={formData.environmentRef}
              onChange={(e) => setFormData({ ...formData, environmentRef: e.target.value })}
              placeholder="Environment référentiel"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
          </div>
        </div>

        {/* Create Button */}
        <button
          type="submit"
          className="w-full py-4 bg-purple-600 hover:bg-purple-700 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2 cursor-pointer"
        >
          <span className="text-xl">+</span>
          Créer la cible
        </button>
      </div>
    </form>
  );
}
