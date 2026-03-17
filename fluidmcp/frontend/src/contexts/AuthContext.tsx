// Auth context provider with lazy loading
import React, { createContext, useContext, useState } from 'react';
import { authService, User, AuthConfig } from '../services/auth';

interface AuthContextType {
  user: User | null;
  authConfig: AuthConfig | null;
  loading: boolean;
  checkAuth: () => Promise<boolean>;
  requireAuth: (returnUrl?: string) => Promise<boolean>;
  logout: () => Promise<void>;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [loading, setLoading] = useState(false);

  // Check if user is authenticated (called on-demand, not on mount)
  const checkAuth = async (): Promise<boolean> => {
    try {
      setLoading(true);

      // Get OAuth config if not already loaded
      if (!authConfig) {
        const config = await authService.getConfig();
        setAuthConfig(config);

        // If OAuth not enabled, allow access
        if (!config.enabled) {
          return true;
        }
      }

      // Check if user is authenticated
      const currentUser = await authService.getCurrentUser();
      setUser(currentUser);
      return !!currentUser;
    } catch (error) {
      console.error('Auth check error:', error);
      return false;
    } finally {
      setLoading(false);
    }
  };

  // Require authentication - redirect to login if not authenticated
  const requireAuth = async (returnUrl?: string): Promise<boolean> => {
    const isAuth = await checkAuth();

    if (!isAuth) {
      // Store return URL in sessionStorage with full path
      // Account for /ui/ base path from vite.config.ts
      if (returnUrl) {
        // If returnUrl doesn't start with /ui/, prepend it
        const fullReturnUrl = returnUrl.startsWith('/ui/') ? returnUrl : `/ui${returnUrl}`;
        sessionStorage.setItem('auth_return_url', fullReturnUrl);
      }
      // Redirect to Auth0 login
      authService.login();
      return false;
    }

    return true;
  };

  const logout = async () => {
    await authService.logout();
    setUser(null);
  };

  const value = {
    user,
    authConfig,
    loading,
    checkAuth,
    requireAuth,
    logout,
    isAuthenticated: !!user
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
