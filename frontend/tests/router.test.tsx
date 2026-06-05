import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
    // stock code rendered (inline chip + right-side annotation)
    expect(screen.getAllByText('3231').length).toBeGreaterThan(0);
  });

  it('redirects unknown paths to /', async () => {
    mockHome();
    renderAt('/nonexistent/path');
    expect(await screen.findByText('動態時間軸')).toBeInTheDocument();
  });

  it('filters the in-page feed when a person chip is clicked (no navigation)', async () => {
    mockHome();
    renderAt('/');
    // both posts visible initially
    expect(await screen.findByText('放棄吧散戶,外面全都是黑k')).toBeInTheDocument();
    expect(screen.getByText('家父持股緯創全數售出')).toBeInTheDocument();

    // click the 爸逆逆 filter chip (the button, not a per-post author link)
    await userEvent.click(screen.getByRole('button', { name: /爸逆逆/ }));

    // only 爸逆逆's post remains; 巴逆逆's is filtered out — still on '/'
    expect(screen.getByText('家父持股緯創全數售出')).toBeInTheDocument();
    expect(screen.queryByText('放棄吧散戶,外面全都是黑k')).not.toBeInTheDocument();
    expect(screen.getByText('動態時間軸')).toBeInTheDocument();
  });

  it('combines the "有提到股票" filter with a person filter', async () => {
    mockHome();
    renderAt('/');
    await screen.findByText('放棄吧散戶,外面全都是黑k');

    // only-stocks: 巴逆逆's no-trade post drops, 爸逆逆's trade post stays
    await userEvent.click(screen.getByRole('button', { name: /有提到股票/ }));
    expect(screen.getByText('家父持股緯創全數售出')).toBeInTheDocument();
    expect(screen.queryByText('放棄吧散戶,外面全都是黑k')).not.toBeInTheDocument();

    // combine with 巴逆逆 (who has no trade posts) → empty result
    await userEvent.click(screen.getByRole('button', { name: /巴逆逆/ }));
    expect(screen.queryByText('家父持股緯創全數售出')).not.toBeInTheDocument();
    expect(screen.getByText('沒有符合篩選條件的貼文。')).toBeInTheDocument();
  });
});
