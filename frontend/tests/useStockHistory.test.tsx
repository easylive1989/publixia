import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { useStockHistory } from '../src/hooks/useStockHistory';

function wrap(initialEntry: string, client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/stock/:code" element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('useStockHistory', () => {
  it('reads ticker from path and range from ?range=', async () => {
    let calledUrl = '';
    server.use(
      http.get('*/api/stocks/2330.TW/history', ({ request }) => {
        calledUrl = request.url;
        return HttpResponse.json({
          ticker: '2330.TW', name: '台積電', currency: 'TWD', time_range: '1Y',
          dates: [], candles: [],
          indicators: {
            ma5: [], ma20: [], ma60: [], rsi14: [],
            macd: [], macd_signal: [], macd_histogram: [],
          },
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useStockHistory(), {
      wrapper: wrap('/stock/2330.TW?range=1Y', client),
    });
    await waitFor(() => expect(result.current.data?.name).toBe('台積電'));
    expect(calledUrl).toContain('time_range=1Y');
  });

  it('defaults range to 3M when query string absent', async () => {
    let calledUrl = '';
    server.use(
      http.get('*/api/stocks/AAPL/history', ({ request }) => {
        calledUrl = request.url;
        return HttpResponse.json({
          ticker: 'AAPL', name: 'Apple', currency: 'USD', time_range: '3M',
          dates: [], candles: [],
          indicators: {
            ma5: [], ma20: [], ma60: [], rsi14: [],
            macd: [], macd_signal: [], macd_histogram: [],
          },
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useStockHistory(), { wrapper: wrap('/stock/AAPL', client) });
    await waitFor(() => expect(calledUrl).toContain('time_range=3M'));
  });
});
