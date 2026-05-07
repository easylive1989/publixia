import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { useMe, useStrategies, useDslSchema } from '../src/hooks/useStrategy';

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const queryClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe('useMe', () => {
  it('returns identity + can_use_strategy + has_webhook', async () => {
    server.use(
      http.get('*/api/me', () =>
        HttpResponse.json({
          user_id: 1, name: 'paul',
          can_use_strategy: true, has_webhook: false,
        }),
      ),
    );
    const { result } = renderHook(() => useMe(), { wrapper: wrapper(queryClient()) });
    await waitFor(() => expect(result.current.data?.name).toBe('paul'));
    expect(result.current.data?.can_use_strategy).toBe(true);
    expect(result.current.data?.has_webhook).toBe(false);
  });
});

describe('useStrategies', () => {
  it('returns the user list', async () => {
    server.use(
      http.get('*/api/strategies', () =>
        HttpResponse.json([
          { id: 1, name: 'rsi_long', state: 'idle', notify_enabled: false },
        ]),
      ),
    );
    const { result } = renderHook(() => useStrategies(), { wrapper: wrapper(queryClient()) });
    await waitFor(() => expect(result.current.data?.length).toBe(1));
    expect(result.current.data?.[0].name).toBe('rsi_long');
  });
});

describe('useDslSchema', () => {
  it('exposes fields / operators / indicators', async () => {
    server.use(
      http.get('*/api/strategies/dsl/schema', () =>
        HttpResponse.json({
          version: 1,
          fields: ['close'],
          operators: ['gt'],
          indicators: [{ name: 'sma', params: [{ name: 'n', type: 'int', min: 1 }] }],
          exit_modes: ['pct', 'points', 'dsl'],
          vars: ['entry_price'],
        }),
      ),
    );
    const { result } = renderHook(() => useDslSchema(), { wrapper: wrapper(queryClient()) });
    await waitFor(() => expect(result.current.data?.indicators[0].name).toBe('sma'));
  });
});
