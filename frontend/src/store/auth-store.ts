import { create } from 'zustand';

interface AuthStore {
  token: string | null;
  setToken: (t: string) => void;
  clearToken: () => void;
}

const STORAGE_KEY = 'sd_token';

export const useAuthStore = create<AuthStore>((set) => ({
  token: localStorage.getItem(STORAGE_KEY),
  setToken: (t) => {
    localStorage.setItem(STORAGE_KEY, t);
    set({ token: t });
  },
  clearToken: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ token: null });
  },
}));
