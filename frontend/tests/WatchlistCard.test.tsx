import { describe, it, expect } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/WatchlistCard';
import { listCards } from '../src/cards/registry';
import type { WatchlistRow } from '../src/hooks/useWatchlist';

function renderCard() {
  const spec = listCards('dashboard').find((c) => c.id === 'watchlist')!;
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Card />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('WatchlistCard (read-only)', () => {
  it('registers as cols=3 dashboard card', () => {
    expect(listCards('dashboard').find((c) => c.id === 'watchlist')?.cols).toBe(3);
  });

  it('renders rows with ticker as a link to /stock/:code', async () => {
    server.use(
      http.get('*/api/stocks', () =>
        HttpResponse.json([
          {
            ticker: '2330.TW',
            name: '台積電',
            price: 1000,
            change: 5,
            change_pct: 0.5,
            currency: 'TWD',
            timestamp: '2026-05-02',
          },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      const link = screen.getByRole('link', { name: '2330.TW' });
      expect(link).toHaveAttribute('href', '/stock/2330.TW');
      expect(screen.getByText('台積電')).toBeInTheDocument();
    });
  });
});

describe('WatchlistCard add form', () => {
  it('typing a ticker and clicking add calls POST /api/stocks then re-fetches', async () => {
    let postCalled: { ticker?: string } = {};
    let stocks: WatchlistRow[] = [];
    server.use(
      http.get('*/api/stocks', () => HttpResponse.json(stocks)),
      http.post('*/api/stocks', async ({ request }) => {
        const body = (await request.json()) as { ticker: string };
        postCalled = body;
        stocks = [
          {
            ticker: body.ticker,
            name: body.ticker,
            price: null,
            change: null,
            change_pct: null,
            currency: null,
            timestamp: null,
          },
        ];
        return HttpResponse.json({ ok: true });
      }),
    );

    renderCard();
    await waitFor(() => expect(screen.getByPlaceholderText(/輸入代號/)).toBeInTheDocument());
    await userEvent.type(screen.getByPlaceholderText(/輸入代號/), '2317.tw');
    await userEvent.click(screen.getByRole('button', { name: '+ 新增' }));

    await waitFor(() => expect(postCalled.ticker).toBe('2317.TW'));
    await waitFor(() =>
      expect(screen.getByRole('link', { name: '2317.TW' })).toBeInTheDocument(),
    );
  });
});

describe('WatchlistCard delete', () => {
  it('clicking × on a row calls DELETE /api/stocks/:ticker and removes the row', async () => {
    let stocks: WatchlistRow[] = [
      { ticker: '2330.TW', name: '台積電', price: 1000, change: 5, change_pct: 0.5, currency: 'TWD', timestamp: '2026-05-02' },
      { ticker: 'AAPL',    name: 'Apple',  price: 200,  change: -1, change_pct: -0.5, currency: 'USD', timestamp: '2026-05-02' },
    ];
    let deletedTicker = '';
    server.use(
      http.get('*/api/stocks', () => HttpResponse.json(stocks)),
      http.delete('*/api/stocks/:ticker', ({ params }) => {
        deletedTicker = decodeURIComponent(params.ticker as string);
        stocks = stocks.filter((s) => s.ticker !== deletedTicker);
        return HttpResponse.json({ ok: true });
      }),
    );

    renderCard();
    await waitFor(() =>
      expect(screen.getByRole('link', { name: '2330.TW' })).toBeInTheDocument(),
    );
    const rows = screen.getAllByRole('row');
    const tsmcRow = rows.find((r) => r.textContent?.includes('2330.TW'))!;
    await userEvent.click(within(tsmcRow).getByRole('button', { name: /移除 2330.TW/ }));

    await waitFor(() => expect(deletedTicker).toBe('2330.TW'));
    await waitFor(() =>
      expect(screen.queryByRole('link', { name: '2330.TW' })).not.toBeInTheDocument(),
    );
  });
});
