import { getMockCibles, generateCibleId } from './campaign-data';
import type { Cible } from '@/types/campaign.types';

// Simulate network latency
const delay = (ms: number = 300) => new Promise(resolve => setTimeout(resolve, ms));

export const mockCiblesApi = {
  findAll: async (): Promise<Cible[]> => {
    await delay();
    return [...getMockCibles()];
  },

  findById: async (id: string): Promise<Cible> => {
    await delay(200);
    const cible = getMockCibles().find(c => c.id === id);
    if (!cible) throw new Error(`Cible ${id} not found`);
    return cible;
  },

  create: async (data: Omit<Cible, 'id' | 'timestamp' | 'code'>): Promise<Cible> => {
    await delay(500);
    const cibles = getMockCibles();
    const newCible: Cible = {
      ...data,
      id: String(cibles.length + 1),
      code: generateCibleId(),
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    };
    cibles.push(newCible);
    return newCible;
  },

  update: async (id: string, data: Partial<Cible>): Promise<Cible> => {
    await delay(400);
    const cibles = getMockCibles();
    const index = cibles.findIndex(c => c.id === id);
    if (index === -1) throw new Error(`Cible ${id} not found`);

    cibles[index] = { ...cibles[index], ...data };
    return cibles[index];
  },

  delete: async (id: string): Promise<void> => {
    await delay(300);
    const cibles = getMockCibles();
    const index = cibles.findIndex(c => c.id === id);
    if (index === -1) throw new Error(`Cible ${id} not found`);
    cibles.splice(index, 1);
  },

  createFromFile: async (nomCible: string, file: File): Promise<Cible> => {
    await delay(1500); // Longer delay to simulate file processing
    const cibles = getMockCibles();
    const newCible: Cible = {
      id: String(cibles.length + 1),
      code: generateCibleId(),
      name: nomCible,
      type: `Fichier: ${file.name}`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    };
    cibles.push(newCible);
    return newCible;
  },
};
