import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import App from '../src/App';
import { useAuthStore } from '../src/store/auth-store';

describe('App integration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('shows TokenGate when no token', () => {
    render(<App />);
    expect(screen.getByPlaceholderText('sd_...')).toBeInTheDocument();
  });

  it('after token entry, renders Dashboard with cards', async () => {
    server.use(
      http.get('*/api/indicators/taiex', () =>
        HttpResponse.json({ date: '2026-05-02', close: 18000, change_pct: 0.5 }),
      ),
    );

    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText('sd_...'), 'sd_test_token');
    await user.click(screen.getByRole('button', { name: '登入' }));

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(useAuthStore.getState().token).toBe('sd_test_token');
  });
});
