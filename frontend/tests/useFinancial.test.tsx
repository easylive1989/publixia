import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { useFinancial } from '../src/hooks/useFinancial';

function wrap(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes>
          <Route path="/stock/:code" element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('useFinancial', () => {
  it('income and balance statements use distinct cache keys', async () => {
    const calls: string[] = [];
    server.use(
      http.get('*/api/stocks/2330.TW/financial', ({ request }) => {
        const u = new URL(request.url);
        calls.push(u.searchParams.get('statement') || '');
        return HttpResponse.json({
          ticker: '2330.TW',
          statement: u.searchParams.get('statement'),
          quarters: 12,
          ok: true,
          rows: [],
          annual_summary: null,
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(
      () => ({ a: useFinancial('income'), b: useFinancial('balance') }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => expect(calls).toContain('income'));
    await waitFor(() => expect(calls).toContain('balance'));
    expect(new Set(calls).size).toBe(2);
  });
});
