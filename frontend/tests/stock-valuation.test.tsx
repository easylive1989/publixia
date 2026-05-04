import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-valuation';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const Card = listCards('stock').find((c) => c.id === 'stock-valuation')!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<Card />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ValuationCard', () => {
  it('shows PER / PBR / yield latest + 5y range + PER percentile', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/valuation', () =>
        HttpResponse.json({
          ticker: '2330.TW',
          years: 5,
          as_of: '2026-04-30',
          ok: true,
          latest: {
            per: 22.5,
            pbr: 6.1,
            dividend_yield: 1.5,
            per_percentile_5y: 80,
          },
          range_5y: {
            per: { min: 12.59, max: 34.19, avg: 22.59 },
            pbr: { min: 4.17, max: 10.84, avg: 6.33 },
            dividend_yield: { min: 0.89, max: 2.22, avg: 1.55 },
          },
          rows: [
            { date: '2025-01-01', per: 20, pbr: 5, dividend_yield: 1.6 },
            { date: '2026-04-01', per: 22.5, pbr: 6.1, dividend_yield: 1.5 },
          ],
        }),
      ),
    );
    renderCard();
    await waitFor(() => expect(screen.getByText('估值快照')).toBeInTheDocument());
    expect(screen.getByText('22.50')).toBeInTheDocument();
    expect(screen.getByText('6.10')).toBeInTheDocument();
    expect(screen.getByText('1.50%')).toBeInTheDocument();
    expect(screen.getByText('5y 百分位 80%')).toBeInTheDocument();
    expect(screen.getByText(/5y 12.59 – 34.19/)).toBeInTheDocument();
  });
});
