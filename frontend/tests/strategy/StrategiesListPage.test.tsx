import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../setup';
import StrategiesListPage from '../../src/pages/StrategiesListPage';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/strategies']}>
        <Routes>
          <Route path="/strategies" element={<StrategiesListPage />} />
          <Route path="/strategies/new" element={<div>NEW PAGE</div>} />
          <Route path="/strategies/:id" element={<div>EDIT PAGE</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StrategiesListPage', () => {
  it('renders the empty state when there are no strategies', async () => {
    server.use(
      http.get('*/api/strategies', () => HttpResponse.json([])),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/還沒有策略/)).toBeInTheDocument(),
    );
  });

  it('renders one card per strategy with state badge + name', async () => {
    server.use(
      http.get('*/api/strategies', () =>
        HttpResponse.json([
          {
            id: 1, user_id: 1,
            name: 'rsi_long', direction: 'long', contract: 'TX',
            contract_size: 1, max_hold_days: null,
            entry_dsl: {}, take_profit_dsl: {}, stop_loss_dsl: {},
            notify_enabled: true,
            state: 'open',
            entry_signal_date: '2026-05-01', entry_fill_date: '2026-05-02',
            entry_fill_price: 17000, pending_exit_kind: null,
            pending_exit_signal_date: null,
            last_error: null, last_error_at: null,
            created_at: '2026-04-01', updated_at: '2026-05-02',
          },
        ]),
      ),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('rsi_long')).toBeInTheDocument(),
    );
    expect(screen.getByText(/在場內/)).toBeInTheDocument();
  });

  it('the "建立策略" button links to /strategies/new', async () => {
    server.use(
      http.get('*/api/strategies', () => HttpResponse.json([])),
    );
    renderPage();
    const link = await screen.findByRole('link', { name: /建立策略/ });
    expect(link).toHaveAttribute('href', '/strategies/new');
  });
});
