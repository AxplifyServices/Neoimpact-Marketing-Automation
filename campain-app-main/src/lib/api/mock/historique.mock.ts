import { getMockHistorique } from './campaign-data';
import type { HistoryRecord } from '@/types/campaign.types';

// Simulate network latency
const delay = (ms: number = 300) => new Promise(resolve => setTimeout(resolve, ms));

export const mockHistoriqueApi = {
  findAll: async (params?: {
    campaign?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
  }): Promise<HistoryRecord[]> => {
    await delay();
    let results = [...getMockHistorique()];

    // Filter by campaign
    if (params?.campaign && params.campaign !== '(Tous)') {
      results = results.filter(r => r.idCampagne === params.campaign);
    }

    // Filter by date range (if implemented)
    // ... date filtering logic

    // Pagination (if implemented)
    if (params?.page && params?.pageSize) {
      const start = (params.page - 1) * params.pageSize;
      const end = start + params.pageSize;
      results = results.slice(start, end);
    }

    return results;
  },

  findById: async (id: string): Promise<HistoryRecord> => {
    await delay(200);
    const record = getMockHistorique().find(r => r.id === id);
    if (!record) throw new Error(`History record ${id} not found`);
    return record;
  },
};
