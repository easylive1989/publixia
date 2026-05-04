import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import StockDetailPage from '../src/pages/StockDetailPage';

function emptyHistory(ticker: string, range: string) {
  return {
    ticker,
    name: '台積電',
    currency: 'TWD',
    time_range: range,
    dates: ['2026-05-02'],
    candles: [{ open: 1000, high: 1010, low: 990, close: 1005, volume: 10000 }],
    indicators: {
      ma5: [null], ma20: [null], ma60: [null], rsi14: [null],
      macd: [null], macd_signal: [null], macd_histogram: [null],
    },
  };
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/stock/:code" element={<StockDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StockDetailPage', () => {
  it('renders header with ticker · name + last data date + currency', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/history', () =>
        HttpResponse.json(emptyHistory('2330.TW', '3M')),
      ),
    );
    renderAt('/stock/2330.TW');
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /2330.TW · 台積電/ })).toBeInTheDocument(),
    );
    expect(screen.getByText(/最後資料日 2026-05-02 · TWD/)).toBeInTheDocument();
  });

  it('range buttons trigger refetch with new ?range=', async () => {
    let calledRange = '';
    server.use(
      http.get('*/api/stocks/2330.TW/history', ({ request }) => {
        const u = new URL(request.url);
        calledRange = u.searchParams.get('time_range') || '';
        return HttpResponse.json(emptyHistory('2330.TW', calledRange));
      }),
    );
    renderAt('/stock/2330.TW?range=3M');
    await waitFor(() => expect(calledRange).toBe('3M'));
    await userEvent.click(screen.getByRole('button', { name: '1Y' }));
    await waitFor(() => expect(calledRange).toBe('1Y'));
  });

  it('renders a back-to-dashboard link in the header', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/history', () =>
        HttpResponse.json(emptyHistory('2330.TW', '3M')),
      ),
    );
    renderAt('/stock/2330.TW');
    const backLink = screen.getByRole('link', { name: /返回/ });
    expect(backLink).toHaveAttribute('href', '/');
  });
});
