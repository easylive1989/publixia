import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/AlertsCard';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const spec = listCards('dashboard').find((c) => c.id === 'alerts')!;
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Card />
    </QueryClientProvider>,
  );
}

describe('AlertsCard (read-only)', () => {
  it('registers as cols=3 dashboard card', () => {
    expect(listCards('dashboard').find((c) => c.id === 'alerts')?.cols).toBe(3);
  });

  it('shows empty placeholder when no alerts', async () => {
    server.use(http.get('*/api/alerts', () => HttpResponse.json([])));
    renderCard();
    await waitFor(() => expect(screen.getByText('尚未設定任何警示')).toBeInTheDocument());
  });

  it('renders an alert row with target label, condition, threshold, status', async () => {
    server.use(
      http.get('*/api/alerts', () =>
        HttpResponse.json([
          {
            id: 1, target_type: 'indicator', target: 'taiex', indicator_key: null,
            condition: 'above', threshold: 18000, window_n: null,
            enabled: 1, created_at: '2026-04-15T00:00:00Z',
            triggered_at: null, triggered_value: null,
          },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('加權指數')).toBeInTheDocument();
      expect(screen.getByText('≥')).toBeInTheDocument();
      expect(screen.getByText('18,000')).toBeInTheDocument();
      expect(screen.getByText('監控中')).toBeInTheDocument();
      expect(screen.getByText(/建立於 2026-04-15/)).toBeInTheDocument();
    });
  });

  it('shows triggered info when triggered_at present', async () => {
    server.use(
      http.get('*/api/alerts', () =>
        HttpResponse.json([
          {
            id: 2, target_type: 'indicator', target: 'taiex', indicator_key: null,
            condition: 'above', threshold: 18000, window_n: null,
            enabled: 0, created_at: '2026-04-15T00:00:00Z',
            triggered_at: '2026-05-01T08:00:00Z', triggered_value: 18234.56,
          },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('已停用')).toBeInTheDocument();
      expect(screen.getByText(/已於 2026-05-01 觸發 \(18,234.56\)/)).toBeInTheDocument();
    });
  });
});

describe('AlertsCard interactions', () => {
  it('clicking 停用 calls PATCH with enabled:false', async () => {
    let patched: any = null;
    let alerts: any[] = [
      {
        id: 5, target_type: 'indicator', target: 'taiex', indicator_key: null,
        condition: 'above', threshold: 18000, window_n: null,
        enabled: 1, created_at: '2026-04-15T00:00:00Z',
        triggered_at: null, triggered_value: null,
      },
    ];
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json(alerts)),
      http.patch('*/api/alerts/:id', async ({ request, params }) => {
        patched = { id: Number(params.id), body: await request.json() };
        alerts = alerts.map((a) => (a.id === Number(params.id) ? { ...a, enabled: 0 } : a));
        return HttpResponse.json({ ok: true });
      }),
    );

    renderCard();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '停用' })).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole('button', { name: '停用' }));
    await waitFor(() => expect(patched).toEqual({ id: 5, body: { enabled: false } }));
  });

  it('clicking ✕ calls DELETE and removes row', async () => {
    let alerts: any[] = [
      {
        id: 9, target_type: 'indicator', target: 'taiex', indicator_key: null,
        condition: 'above', threshold: 18000, window_n: null,
        enabled: 1, created_at: '2026-04-15T00:00:00Z',
        triggered_at: null, triggered_value: null,
      },
    ];
    let deletedId = 0;
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json(alerts)),
      http.delete('*/api/alerts/:id', ({ params }) => {
        deletedId = Number(params.id);
        alerts = alerts.filter((a) => a.id !== deletedId);
        return HttpResponse.json({ ok: true });
      }),
    );

    renderCard();
    await waitFor(() => expect(screen.getByText('加權指數')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /刪除警示 9/ }));
    await waitFor(() => expect(deletedId).toBe(9));
    await waitFor(() => expect(screen.queryByText('加權指數')).not.toBeInTheDocument());
  });
});
