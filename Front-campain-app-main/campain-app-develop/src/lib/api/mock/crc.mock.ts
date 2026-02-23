import { getMockCRCActions } from './campaign-data';
import type { Action } from '@/types/campaign.types';

// Simulate network latency
const delay = (ms: number = 300) => new Promise(resolve => setTimeout(resolve, ms));

export const mockCrcApi = {
  findAll: async (params?: {
    campaign?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<Action[]> => {
    await delay();
    let results = [...getMockCRCActions()];

    // Filter by campaign
    if (params?.campaign) {
      results = results.filter(a => a.campaignId === params.campaign);
    }

    // Filter by status (traitement)
    if (params?.status) {
      results = results.filter(a => a.traitement === params.status);
    }

    // Pagination (if implemented)
    if (params?.page && params?.pageSize) {
      const start = (params.page - 1) * params.pageSize;
      const end = start + params.pageSize;
      results = results.slice(start, end);
    }

    return results;
  },

  findById: async (id: string): Promise<Action> => {
    await delay(200);
    const action = getMockCRCActions().find(a => a.id === id);
    if (!action) throw new Error(`CRC action ${id} not found`);
    return action;
  },

  updateStatus: async (id: string, traite: string): Promise<Action> => {
    await delay(400);
    const actions = getMockCRCActions();
    const index = actions.findIndex(a => a.id === id);
    if (index === -1) throw new Error(`CRC action ${id} not found`);

    actions[index] = { ...actions[index], traitement: traite };
    return actions[index];
  },
};
