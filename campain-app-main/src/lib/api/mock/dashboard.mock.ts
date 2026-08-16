import { mockDashboardStats, mockChartData, CHART_COLORS } from './campaign-data';
import type { StatCard, ChartDataPoint, PerformanceDataPoint } from '@/types/campaign.types';

// Simulate network latency
const delay = (ms: number = 300) => new Promise(resolve => setTimeout(resolve, ms));

export const mockDashboardApi = {
  getStats: async (): Promise<Omit<StatCard, 'icon'>[]> => {
    await delay(200);
    return mockDashboardStats;
  },

  getMixInteractions: async (): Promise<ChartDataPoint[]> => {
    await delay(200);
    return mockChartData.mixInteractions;
  },

  getCanalDistribution: async (): Promise<ChartDataPoint[]> => {
    await delay(200);
    return mockChartData.canalDistribution;
  },

  getPerformanceMetrics: async (): Promise<PerformanceDataPoint[]> => {
    await delay(200);
    return mockChartData.performance;
  },

  getTendency: async (): Promise<ChartDataPoint[]> => {
    await delay(200);
    return mockChartData.tendency;
  },

  getConversionFunnel: async (): Promise<ChartDataPoint[]> => {
    await delay(200);
    return mockChartData.conversion;
  },

  getRegionalDistribution: async (): Promise<ChartDataPoint[]> => {
    await delay(200);
    return mockChartData.regional;
  },

  getColors: (): string[] => {
    return CHART_COLORS;
  },
};
