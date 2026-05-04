import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-revenue';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const Card = listCards('stock').find((c) => c.id === 'stock-revenue')!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<Card />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('RevenueCard', () => {
  it('renders title and empty placeholder when rows empty', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/revenue', () =>
        HttpResponse.json({ ticker: '2330.TW', months: 36, ok: true, rows: [] }),
      ),
    );
    renderCard();
    await waitFor(() => expect(screen.getByText('月營收')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('尚無資料')).toBeInTheDocument());
  });
});
