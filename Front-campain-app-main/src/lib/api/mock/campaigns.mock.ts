import { getMockCampaigns, getMockCampaignStats, generateCampaignId } from './campaign-data';
import type { Campaign, Stat } from '@/types/campaign.types';

// Simulate network latency
const delay = (ms: number = 300) => new Promise(resolve => setTimeout(resolve, ms));

export const mockCampaignsApi = {
  findAll: async (params?: { search?: string; status?: string }): Promise<Campaign[]> => {
    await delay();
    let results = [...getMockCampaigns()];

    if (params?.search) {
      results = results.filter(c =>
        c.title.toLowerCase().includes(params.search!.toLowerCase()) ||
        c.code.toLowerCase().includes(params.search!.toLowerCase())
      );
    }

    if (params?.status) {
      results = results.filter(c => c.status === params.status);
    }

    return results;
  },

  findById: async (id: string): Promise<Campaign> => {
    await delay(200);
    const campaign = getMockCampaigns().find(c => c.id === id);
    if (!campaign) throw new Error(`Campaign ${id} not found`);
    return campaign;
  },

  getStats: async (): Promise<Stat[]> => {
    await delay(200);
    return getMockCampaignStats();
  },

  create: async (data: Omit<Campaign, 'id'>): Promise<Campaign> => {
    await delay(500);
    const campaigns = getMockCampaigns();
    const newCampaign: Campaign = {
      ...data,
      id: String(campaigns.length + 1),
      code: data.code || generateCampaignId(),
    };
    campaigns.push(newCampaign);
    return newCampaign;
  },

  update: async (id: string, data: Partial<Campaign>): Promise<Campaign> => {
    await delay(400);
    const campaigns = getMockCampaigns();
    const index = campaigns.findIndex(c => c.id === id);
    if (index === -1) throw new Error(`Campaign ${id} not found`);

    campaigns[index] = { ...campaigns[index], ...data };
    return campaigns[index];
  },

  delete: async (id: string): Promise<void> => {
    await delay(300);
    const campaigns = getMockCampaigns();
    const index = campaigns.findIndex(c => c.id === id);
    if (index === -1) throw new Error(`Campaign ${id} not found`);
    campaigns.splice(index, 1);
  },
};
