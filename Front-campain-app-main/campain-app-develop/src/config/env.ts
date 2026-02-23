// Environment configuration for API integration
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8082/api';
export const AUTH_URL = import.meta.env.VITE_AUTH_URL || 'http://localhost:8080';
export const API_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT) || 30000;

// Feature flags
export const ENABLE_MOCK_DATA = import.meta.env.VITE_ENABLE_MOCK_DATA !== 'false'; // Default true
