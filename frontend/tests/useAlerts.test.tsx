import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import {
  useAlerts, useCreateAlert, useDeleteAlert, useToggleAlert,
} from '../src/hooks/useAlerts';

function wrap(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe('useAlerts CRUD', () => {
  it('createAlert invalidates ["alerts"] (refetches once)', async () => {
    let calls = 0;
    let list: any[] = [];
    server.use(
      http.get('*/api/alerts', () => { calls += 1; return HttpResponse.json(list); }),
      http.post('*/api/alerts', async ({ request }) => {
        const body = (await request.json()) as any;
        list = [{
          id: 1, ...body, indicator_key: null, window_n: null,
          enabled: 1, created_at: '2026-05-03', triggered_at: null, triggered_value: null,
        }];
        return HttpResponse.json({ id: 1 });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => ({ q: useAlerts(), m: useCreateAlert() }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => expect(result.current.q.data).toEqual([]));
    await act(async () => {
      await result.current.m.mutateAsync({
        target_type: 'indicator', target: 'taiex', condition: 'above', threshold: 18000,
      });
    });
    await waitFor(() => expect(calls).toBe(2));
    expect(result.current.q.data?.[0].target).toBe('taiex');
  });

  it('toggleAlert PATCHes with {enabled}', async () => {
    let patched: any = null;
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json([])),
      http.patch('*/api/alerts/:id', async ({ request, params }) => {
        patched = { id: Number(params.id), body: await request.json() };
        return HttpResponse.json({ ok: true });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useToggleAlert(), { wrapper: wrap(client) });
    await act(async () => { await result.current.mutateAsync({ id: 7, enabled: false }); });
    expect(patched).toEqual({ id: 7, body: { enabled: false } });
  });

  it('deleteAlert DELETEs the id', async () => {
    let deletedId = 0;
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json([])),
      http.delete('*/api/alerts/:id', ({ params }) => {
        deletedId = Number(params.id);
        return HttpResponse.json({ ok: true });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useDeleteAlert(), { wrapper: wrap(client) });
    await act(async () => { await result.current.mutateAsync(3); });
    expect(deletedId).toBe(3);
  });
});
