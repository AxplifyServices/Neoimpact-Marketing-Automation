import type { ApiRequest } from '../ApiRequest';

export const clientsApi = {
  // Get all clients using data/read endpoint
  findAll: (limit: number = 100, offset: number = 0): ApiRequest => ({
    url: '/data/read',
    method: 'POST',
    body: {
      table: 'clients',
      limit,
      offset,
    },
  }),

  // Get client by ID using data/read with filter
  findById: (id: string): ApiRequest => ({
    url: '/data/read',
    method: 'POST',
    body: {
      table: 'clients',
      filters: {
        ID_Client: {
          categorical: [id],
        },
      },
      limit: 1,
      offset: 0,
    },
  }),

  // Create new client (uses POST /clients endpoint if available)
  create: (data: any): ApiRequest => ({
    url: '/clients',
    method: 'POST',
    body: data,
  }),

  // Update client (uses PUT /clients/:id endpoint if available)
  update: (id: string, data: any): ApiRequest => ({
    url: `/clients/${id}`,
    method: 'PUT',
    body: data,
  }),

  // Update client cell by cell using data/update-cell
  updateCell: (data: {
    rowid: number;
    col: string;
    value: string | number;
  }): ApiRequest => ({
    url: '/data/update-cell',
    method: 'POST',
    body: {
      table: 'clients',
      rowid: data.rowid,
      col: data.col,
      value: data.value,
    },
  }),

  // Get distinct values for a column
  getDistinctValues: (column: string): ApiRequest => ({
    url: `/data/tables/clients/distinct`,
    method: 'GET',
    params: { col: column },
  }),
};
