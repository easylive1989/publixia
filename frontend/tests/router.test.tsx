import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import DashboardPage from '../src/pages/DashboardPage';
import StockDetailPage from '../src/pages/StockDetailPage';
import '../src/cards/index';

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/stock/:code" element={<StockDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('routing', () => {
  it('renders DashboardPage at /', () => {
    server.use(
      http.get('*/api/indicators/taiex', () =>
        HttpResponse.json({ date: '2026-05-02', close: 100, change_pct: 0 }),
      ),
    );
    renderAt('/');
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('renders StockDetailPage at /stock/:code with code', () => {
    renderAt('/stock/2330');
    expect(screen.getByRole('heading', { name: '2330' })).toBeInTheDocument();
  });

  it('redirects unknown paths to /', () => {
    server.use(
      http.get('*/api/indicators/taiex', () =>
        HttpResponse.json({ date: '2026-05-02', close: 100, change_pct: 0 }),
      ),
    );
    renderAt('/nonexistent/path');
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });
});
