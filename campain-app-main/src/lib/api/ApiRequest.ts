export interface ApiRequest {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  params?: Record<string, any>;
  body?: any;
  pathVariables?: Record<string, string | number>;
  headers?: Record<string, string>;
  useLoader?: boolean;
  responseType?: 'json' | 'blob';
}

export class ApiError extends Error {
  status: number;
  data: any;
  statusText: string;

  constructor(
    status: number,
    data: any,
    statusText: string
  ) {
    super(`API Error: ${status} ${statusText}`);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    this.statusText = statusText;
  }
}

export interface Page<T> {
  number: number;
  content: T[];
  totalPages: number;
  totalElements: number;
}