import { API_BASE_URL, API_TIMEOUT } from "@/config/env";
import type { ApiRequest } from "@/lib/api/ApiRequest";

export class ApiClient {
  private tokenGetter: (() => string | null) | null = null;
  private timeout: number = API_TIMEOUT;

  setTokenGetter(getter: () => string | null) {
    this.tokenGetter = getter;
  }

  getToken(): string | null {
    return this.tokenGetter ? this.tokenGetter() : null;
  }

  private buildUrl(url: string, params?: Record<string, any>) {
    let fullUrl = url.startsWith("http") ? url : `${API_BASE_URL}${url}`;

    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          // Handle arrays by appending each element separately
          if (Array.isArray(value)) {
            value.forEach(item => {
              searchParams.append(key, String(item));
            });
          } else {
            searchParams.append(key, String(value));
          }
        }
      });
      const queryString = searchParams.toString();
      if (queryString) {
        fullUrl += (fullUrl.includes('?') ? '&' : '?') + queryString;
      }
    }

    return fullUrl;
  }

  async request<T>(req: ApiRequest): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    const token = this.getToken();

    // Check if body is FormData or File
    const isFormData = req.body instanceof FormData;
    const isFile = req.body instanceof File;

    // Prepare FormData if body is a File
    let requestBody: any = req.body;
    if (isFile) {
      const formData = new FormData();
      formData.append('file', req.body as File);
      requestBody = formData;
    }

    // Don't set Content-Type for FormData/File uploads (browser will set it with boundary)
    const headers: Record<string, string> = {
      ...(!(isFormData || isFile) ? { "Content-Type": "application/json" } : {}),
      ...(req.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    // Remove Content-Type if it was explicitly set to multipart/form-data
    if (headers["Content-Type"] === "multipart/form-data") {
      delete headers["Content-Type"];
    }

    try {
      const res = await fetch(this.buildUrl(req.url, req.params), {
        method: req.method,
        headers,
        signal: controller.signal,
        body: requestBody
          ? (isFormData || isFile ? requestBody : JSON.stringify(requestBody))
          : undefined,
      });

      clearTimeout(timeoutId);

      // Handle blob responses (for images, files, etc.)
      if (req.responseType === 'blob') {
        if (!res.ok) {
          const text = await res.text();
          const payload = text ? JSON.parse(text) : null;
          const error = new Error(payload?.message || `Request failed: ${res.status}`) as any;
          error.response = {
            status: res.status,
            data: payload,
          };
          error.code = 'API_ERROR';
          throw error;
        }
        return (await res.blob()) as T;
      }

      const text = await res.text();
      const payload = text ? JSON.parse(text) : null;

      if (!res.ok) {
        const error = new Error(payload?.message || `Request failed: ${res.status}`) as any;
        error.response = {
          status: res.status,
          data: payload,
        };
        error.code = 'API_ERROR';
        throw error;
      }

      return payload;
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        const error = new Error('Request timeout') as any;
        error.code = 'ECONNABORTED';
        throw error;
      }
      // Network errors
      if (err instanceof TypeError && err.message.includes('fetch')) {
        const error = new Error('Network error. Please check your connection.') as any;
        error.code = 'ERR_NETWORK';
        throw error;
      }
      throw err;
    }
  }
}

let apiClient: ApiClient | null = null;

export const getApiClient = () => {
  if (!apiClient) apiClient = new ApiClient();
  return apiClient;
};
