import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { apiFetch, ApiError } from '../src/lib/api-client';
import { useAuthStore } from '../src/store/auth-store';

describe('apiFetch', () => {
  beforeEach(() => {
    useAuthStore.setState({ token: 'sd_test' });
  });

  it('injects Authorization Bearer header', async () => {
    let captured = '';
    server.use(
      http.get('*/api/dashboard', ({ request }) => {
        captured = request.headers.get('authorization') || '';
        return HttpResponse.json({ ok: true });
      })
    );

    await apiFetch('/api/dashboard');
    expect(captured).toBe('Bearer sd_test');
  });

  it('returns parsed JSON', async () => {
    server.use(
      http.get('*/api/dashboard', () => HttpResponse.json({ value: 42 }))
    );
    const data = await apiFetch<{ value: number }>('/api/dashboard');
    expect(data).toEqual({ value: 42 });
  });

  it('on 401 clears token and throws ApiError', async () => {
    server.use(
      http.get('*/api/dashboard', () => new HttpResponse(null, { status: 401 }))
    );

    await expect(apiFetch('/api/dashboard')).rejects.toBeInstanceOf(ApiError);
    expect(useAuthStore.getState().token).toBeNull();
  });

  it('on non-2xx (other) throws ApiError with status', async () => {
    server.use(
      http.get('*/api/dashboard', () => HttpResponse.text('boom', { status: 500 }))
    );

    await expect(apiFetch('/api/dashboard')).rejects.toMatchObject({
      status: 500,
    });
  });
});
