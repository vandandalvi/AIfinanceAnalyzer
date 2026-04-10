// API configuration for different environments
// Updated: Using correct Render backend URL
const API_BASE_URL = import.meta.env.PROD 
  ? (import.meta.env.VITE_API_URL || 'https://personalfinanceadvisor.onrender.com')
  : 'http://localhost:5000';

export const API_ENDPOINTS = {
  upload: `${API_BASE_URL}/upload`,
  dashboard: `${API_BASE_URL}/dashboard`,
  chat: `${API_BASE_URL}/chat`,
  advancedAnalytics: `${API_BASE_URL}/advanced-analytics`,
  exportCsv: `${API_BASE_URL}/export/transactions.csv`,
  exportReport: `${API_BASE_URL}/export/report.json`,
};

export default API_BASE_URL;