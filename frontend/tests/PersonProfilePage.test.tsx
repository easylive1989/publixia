import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import PersonProfilePage from '../src/pages/PersonProfilePage';

function renderProfile(personKey: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/people/${personKey}`]}>
        <Routes>
          <Route path="/people/:personKey" element={<PersonProfilePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockPerson() {
  server.use(
    http.get('*/api/people/dadnini', () =>
      HttpResponse.json({
        person_key: 'dadnini',
        display_name: '爸逆逆',
        avatar_url: null,
        accounts: [
          { platform: 'threads', handle: 'ajhsu0820', profile_url: 'https://www.threads.com/@ajhsu0820' },
        ],
      }),
    ),
    http.get('*/api/people/dadnini/posts', () =>
      HttpResponse.json({
        person_key: 'dadnini',
        posts: [
          {
            id: 1,
            platform: 'threads',
            platform_post_id: 'P1',
            url: 'https://www.threads.com/@ajhsu0820/post/P1',
            content: '家父持股緯創全數售出，僅留一張',
            posted_at: '2026-06-03T10:00:00',
            extraction_status: 'done',
            trades: [
              {
                raw_symbol: '緯創',
                ticker: '3231',
                market: 'TW',
                direction: 'sell',
                price: null,
                quantity: 1,
                trade_date: null,
                confidence: 0.92,
              },
            ],
          },
        ],
      }),
    ),
  );
}

describe('PersonProfilePage', () => {
  it('renders header, post timeline and inline trade chip with source link', async () => {
    mockPerson();
    renderProfile('dadnini');

    // header
    expect(await screen.findByRole('heading', { name: '爸逆逆' })).toBeInTheDocument();
    expect(screen.getByText('@ajhsu0820')).toBeInTheDocument();

    // post content + trade chip
    expect(await screen.findByText('家父持股緯創全數售出，僅留一張')).toBeInTheDocument();
    expect(await screen.findAllByText('賣出')).not.toHaveLength(0);
    expect(screen.getAllByText('3231').length).toBeGreaterThan(0);

    // source-evidence link to the original post
    const link = screen.getByText('看原文').closest('a');
    expect(link).toHaveAttribute('href', 'https://www.threads.com/@ajhsu0820/post/P1');
  });

  it('shows not-found message for unknown person', async () => {
    server.use(
      http.get('*/api/people/ghost', () => new HttpResponse(null, { status: 404 })),
      http.get('*/api/people/ghost/posts', () => new HttpResponse(null, { status: 404 })),
    );
    renderProfile('ghost');
    expect(await screen.findByText('找不到這個追蹤對象。')).toBeInTheDocument();
  });
});
