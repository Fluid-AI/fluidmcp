// Auth service for backend OAuth endpoints
import { apiClient } from './api';

export interface User {
  user_id: string;
  email: string;
  name: string;
  picture?: string;
}

export interface AuthConfig {
  enabled: boolean;
  domain: string;
  clientId: string;
}

export const authService = {
  // Check if OAuth is enabled on backend
  async getConfig(): Promise<AuthConfig> {
    return apiClient.getAuthConfig();
  },

  // Get current user info (checks authentication)
  async getCurrentUser(): Promise<User | null> {
    try {
      return await apiClient.getCurrentUser();
    } catch (error) {
      // 401 means not authenticated
      return null;
    }
  },

  // Redirect to Auth0 login (backend handles OAuth flow)
  login() {
    window.location.href = '/auth/login';
  },

  // Logout and clear cookie
  async logout() {
    try {
      const response = await apiClient.logout();
      // Use logout_url from backend (redirects to Auth0 logout, then back to /ui)
      if (response?.logout_url) {
        window.location.href = response.logout_url;
      } else {
        // Fallback to /ui if no logout_url provided
        window.location.href = '/ui';
      }
    } catch (error) {
      // If logout fails, still redirect to /ui
      window.location.href = '/ui';
    }
  }
};
