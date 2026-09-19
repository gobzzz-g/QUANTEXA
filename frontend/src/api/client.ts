import axios from 'axios';

export const apiClient = axios.create({
  baseURL: '/api',
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Extract a safe error message
    const message = error.response?.data?.detail || error.message || "Unable to connect to the analytics API.";
    // Ensure we throw a standard Error object with the extracted message
    return Promise.reject(new Error(message));
  }
);
