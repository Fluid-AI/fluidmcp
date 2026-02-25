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
    await apiClient.logout();
    window.location.href = '/';
  }
};
