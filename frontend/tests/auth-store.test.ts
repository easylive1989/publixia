import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from '../src/store/auth-store';

describe('auth-store', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ token: null });
  });

  it('setToken persists to localStorage and updates state', () => {
    useAuthStore.getState().setToken('sd_new');
    expect(localStorage.getItem('sd_token')).toBe('sd_new');
    expect(useAuthStore.getState().token).toBe('sd_new');
  });

  it('clearToken removes from localStorage and resets state', () => {
    useAuthStore.getState().setToken('sd_x');
    useAuthStore.getState().clearToken();
    expect(localStorage.getItem('sd_token')).toBeNull();
    expect(useAuthStore.getState().token).toBeNull();
  });

});
