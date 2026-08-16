import type { ApiRequest } from '../ApiRequest';

export const dataApi = {
  // Get all available tables
  getTables: (): ApiRequest => ({
    url: '/data/tables',
    method: 'GET',
  }),

  // Get columns for a specific table
  getTableColumns: (table: string): ApiRequest => ({
    url: `/data/tables/${table}/columns`,
    method: 'GET',
  }),

  // Get distinct values for a column
  getDistinctValues: (table: string, col: string): ApiRequest => ({
    url: `/data/tables/${table}/distinct`,
    method: 'GET',
    params: { col },
  }),

  // Read table data with filters
  readTableData: (data: {
    table: string;
    filters?: Record<string, { categorical?: string[]; numeric?: { min?: number; max?: number } }>;
    limit?: number;
    offset?: number;
  }): ApiRequest => ({
    url: '/data/read',
    method: 'POST',
    body: data,
  }),

  // Update a single cell
  updateCell: (data: {
    table: string;
    rowid: number;
    col: string;
    value: string | number;
  }): ApiRequest => ({
    url: '/data/update-cell',
    method: 'POST',
    body: data,
  }),
};
