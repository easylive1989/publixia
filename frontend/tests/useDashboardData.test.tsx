import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { useDashboardData } from '../src/hooks/useDashboardData';

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe('useDashboardData', () => {
  it('returns parsed indicator dict on success', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          taiex: { value: 18000, timestamp: '2026-05-02T08:00:00Z', extra: { change_pct: 1.2 } },
        }),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useDashboardData(), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.data?.taiex.value).toBe(18000));
  });

  it('two consumers share one fetch (dedupe via TanStack Query cache)', async () => {
    let calls = 0;
    server.use(
      http.get('*/api/dashboard', () => {
        calls += 1;
        return HttpResponse.json({});
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(
      () => {
        useDashboardData();
        useDashboardData();
      },
      { wrapper: wrapper(client) },
    );
    await waitFor(() => expect(calls).toBe(1));
  });
});
