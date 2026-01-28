/**
 * Authentication state management with Zustand
 * Note: All authentication is now handled through Dify API
 * This store only manages local auth state
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { AuthState } from '@/types/auth';

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      login: async (credentials: { username: string; password: string }) => {
        // Login is now handled through Dify chat
        // This method is kept for compatibility but should not be called directly
        console.warn('Login should be handled through Dify chat interface');
        throw new Error('Please use Dify chat interface for login');
      },

      register: async (data: { username: string; email: string; password: string }) => {
        // Registration is now handled through Dify chat
        console.warn('Registration should be handled through Dify chat interface');
        throw new Error('Please use Dify chat interface for registration');
      },

      logout: () => {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        set({
          user: null,
          token: null,
          isAuthenticated: false,
        });
      },

      setUser: (user) => {
        set({ user, isAuthenticated: true });
      },

      // New method to set auth state from Dify response
      setAuthFromDify: (user: any, token: string) => {
        localStorage.setItem('token', token);
        localStorage.setItem('user', JSON.stringify(user));
        set({
          user,
          token,
          isAuthenticated: true,
        });
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
