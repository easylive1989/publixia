import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import HomePage from '../src/pages/HomePage';

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockHome() {
  server.use(
    http.get('*/api/people', () =>
      HttpResponse.json({
        people: [
          { person_key: 'dadnini', display_name: '爸逆逆', avatar_url: null, platforms: ['threads'], latest_post_at: '2026-06-03T10:00:00', trade_count: 5 },
          { person_key: 'banini', display_name: '巴逆逆', avatar_url: null, platforms: ['threads'], latest_post_at: '2026-06-04T10:00:00', trade_count: 2 },
        ],
      }),
    ),
    http.get('*/api/timeline', () =>
      HttpResponse.json({
        posts: [
          {
            id: 1, platform: 'threads', platform_post_id: 'P1',
            url: 'https://www.threads.com/@banini31/post/P1',
            content: '放棄吧散戶,外面全都是黑k', posted_at: '2026-06-04T10:00:00',
            extraction_status: 'done',
            person: { person_key: 'banini', display_name: '巴逆逆', avatar_url: null },
            trades: [],
          },
          {
            id: 2, platform: 'threads', platform_post_id: 'P2',
            url: 'https://www.threads.com/@ajhsu0820/post/P2',
            content: '家父持股緯創全數售出', posted_at: '2026-06-03T10:00:00',
            extraction_status: 'done',
            person: { person_key: 'dadnini', display_name: '爸逆逆', avatar_url: null },
            trades: [{ raw_symbol: '緯創', ticker: '3231', market: 'TW', direction: 'sell', price: null, quantity: null, trade_date: null, confidence: 0.9 }],
          },
        ],
      }),
    ),
  );
}

describe('routing', () => {
  it('renders the merged timeline at / with posts from multiple people', async () => {
    mockHome();
    renderAt('/');
    expect(screen.getByText('動態時間軸')).toBeInTheDocument();
    // both people's posts appear in one feed
    expect(await screen.findByText('放棄吧散戶,外面全都是黑k')).toBeInTheDocument();
    expect(await screen.findByText('家父持股緯創全數售出')).toBeInTheDocument();
    // author labels present (people strip + per-post author → multiple matches)
    expect(screen.getAllByText('爸逆逆').length).toBeGreaterThan(0);
    expect(screen.getAllByText('巴逆逆').length).toBeGreaterThan(0);
    // a trade chip rendered inline
    expect(screen.getByText('3231')).toBeInTheDocument();
  });

  it('redirects unknown paths to /', async () => {
    mockHome();
    renderAt('/nonexistent/path');
    expect(await screen.findByText('動態時間軸')).toBeInTheDocument();
  });
});
