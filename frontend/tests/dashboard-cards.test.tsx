import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/dashboard-cards';
import { listCards } from '../src/cards/registry';
import { useRangeStore } from '../src/store/range-store';

function renderCard(id: string) {
  const spec = listCards('dashboard').find((c) => c.id === id);
  if (!spec) throw new Error(`card ${id} not registered`);
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Card />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useRangeStore.setState({ range: '3M' });
  // Default empty history so cards don't try to hit the network.
  server.use(
    http.get('*/api/history/:indicator', () => HttpResponse.json([])),
  );
});

describe('dashboard-cards', () => {
  it('registers 12 cards on the dashboard page', () => {
    expect(listCards('dashboard').length).toBe(12);
  });

  it('taiex renders main value + change_pct badge + prev_close in sub', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          taiex: {
            value: 18234.56,
            timestamp: '2026-05-02T08:00:00Z',
            extra: { change_pct: 1.23, prev_close: 18011 },
          },
        }),
      ),
    );
    renderCard('taiex');
    await waitFor(() => {
      expect(screen.getByText('18,234.56')).toBeInTheDocument();
      expect(screen.getByText('▲ +1.23%')).toBeInTheDocument();
      expect(screen.getByText(/前收 18,011/)).toBeInTheDocument();
    });
  });

  it('total_foreign_net colors red when negative', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          total_foreign_net: { value: -5.5, timestamp: '2026-05-02T00:00:00Z', extra: {} },
        }),
      ),
    );
    renderCard('total_foreign_net');
    await waitFor(() => {
      expect(screen.getByText('-5.50 億')).toHaveClass('text-red-600');
    });
  });

  it('ndc shows period in sub line and light as badge', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          ndc: { value: 28, timestamp: '2026-05-02T00:00:00Z', extra: { period: '2026-04', light: '綠燈' } },
        }),
      ),
    );
    renderCard('ndc');
    await waitFor(() => {
      expect(screen.getByText('28 分')).toBeInTheDocument();
      expect(screen.getByText(/2026-04 · 每月更新/)).toBeInTheDocument();
      expect(screen.getByText('綠燈')).toBeInTheDocument();
    });
  });

  it('renders sparkline when /api/history returns ≥2 points', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          taiex: { value: 18000, timestamp: '2026-05-02T08:00:00Z', extra: {} },
        }),
      ),
      http.get('*/api/history/taiex', () =>
        HttpResponse.json([
          { timestamp: '2026-04-30T08:00:00Z', value: 17800 },
          { timestamp: '2026-05-01T08:00:00Z', value: 17900 },
          { timestamp: '2026-05-02T08:00:00Z', value: 18000 },
        ]),
      ),
    );
    renderCard('taiex');
    await waitFor(() => {
      expect(screen.getByTestId('spark')).toBeInTheDocument();
    });
  });

  it('omits sparkline when /api/history returns empty', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          taiex: { value: 18000, timestamp: '2026-05-02T08:00:00Z', extra: {} },
        }),
      ),
    );
    renderCard('taiex');
    await waitFor(() => expect(screen.getByText('18,000')).toBeInTheDocument());
    expect(screen.queryByTestId('spark')).toBeNull();
  });
});
