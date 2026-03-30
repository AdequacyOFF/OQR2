import { create } from 'zustand';
import api from '../api/client';
import type { UserInfo, AuthResponse } from '../types';

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: {
    email: string;
    password: string;
    role: string;
    full_name: string;
    school?: string;
    grade?: number;
    institution_id?: string;
    institution_location?: string;
    is_captain?: boolean;
    dob?: string;
  }) => Promise<void>;
  logout: () => void;
  loadFromStorage: () => Promise<void>;
}

const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,

  login: async (email: string, password: string) => {
    const { data } = await api.post<AuthResponse>('auth/login', { email, password });

    localStorage.setItem('access_token', data.access_token);
    set({ token: data.access_token });

    const { data: user } = await api.get<UserInfo>('auth/me');
    set({ user, isAuthenticated: true });
  },

  register: async (data) => {
    const { data: authData } = await api.post<AuthResponse>('auth/register', data);

    localStorage.setItem('access_token', authData.access_token);
    set({ token: authData.access_token });

    const { data: user } = await api.get<UserInfo>('auth/me');
    set({ user, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('access_token');
    set({ token: null, user: null, isAuthenticated: false });
  },

  loadFromStorage: async () => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    set({ token });
    try {
      const { data: user } = await api.get<UserInfo>('auth/me');
      set({ user, isAuthenticated: true });
    } catch {
      localStorage.removeItem('access_token');
      set({ token: null, user: null, isAuthenticated: false });
    }
  },
}));

export default useAuthStore;
