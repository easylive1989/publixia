import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import ScoreboardPage from '../src/pages/ScoreboardPage';
import TimelinePage from '../src/pages/TimelinePage';

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<ScoreboardPage />} />
          <Route path="/timeline" element={<TimelinePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockApi() {
  server.use(
    http.get('*/api/scoreboard', () =>
      HttpResponse.json({
        standings: [
          { person_key: 'dadnini', display_name: '爸逆逆', win_count: 2, loss_count: 1, signal_count: 3, win_rate: 2 / 3, cum_return: 0.13, form: ['w', 'l', 'w'], dnp: false, rank: 1 },
          { person_key: 'banini', display_name: '巴逆逆', win_count: 0, loss_count: 0, signal_count: 0, win_rate: null, cum_return: null, form: [], dnp: true, rank: null },
        ],
      }),
    ),
    http.get('*/api/timeline', () =>
      HttpResponse.json({
        posts: [
          {
            id: 1, platform: 'threads', platform_post_id: 'P1', url: 'https://t/p/P1',
            content: '巴逆逆隨手發言沒喊單', posted_at: '2026-06-04T10:00:00',
            extraction_status: 'done', title: null,
            person: { person_key: 'banini', display_name: '巴逆逆', avatar_url: null },
            trades: [],
          },
          {
            id: 2, platform: 'threads', platform_post_id: 'P2', url: 'https://t/p/P2',
            content: '家父買進台積電', posted_at: '2026-06-03T10:00:00',
            extraction_status: 'done', title: null,
            person: { person_key: 'dadnini', display_name: '爸逆逆', avatar_url: null },
            trades: [{
              raw_symbol: '台積電', ticker: '2330', market: 'TW', stock_name: '台積電',
              direction: 'buy', price: null, quantity: null, trade_date: null, confidence: 0.9,
              pct_latest: 0.05, pct_7d: null, pct_1m: null, base_price: 100, price_status: 'partial',
            }],
          },
        ],
      }),
    ),
  );
}

describe('scoreboard app', () => {
  it('renders standings + play-by-play with verdicts at /', async () => {
    mockApi();
    renderAt('/');
    expect(screen.getByText('戰績排行榜')).toBeInTheDocument();
    // standings: win-rate and cumulative P&L
    expect(await screen.findByText('67%')).toBeInTheDocument();
    expect(screen.getByText('+13.0%')).toBeInTheDocument();
    // play-by-play verdict on the winning buy
    expect(await screen.findByText('家父買進台積電')).toBeInTheDocument();
    expect(screen.getByText('跟單賺')).toBeInTheDocument();
    expect(screen.getByText('WIN')).toBeInTheDocument();
    // no-call post shows NO CALL
    expect(screen.getByText('NO CALL')).toBeInTheDocument();
  });

  it('filters the feed when a person tab is clicked (no navigation)', async () => {
    mockApi();
    renderAt('/');
    expect(await screen.findByText('巴逆逆隨手發言沒喊單')).toBeInTheDocument();
    expect(screen.getByText('家父買進台積電')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /爸逆逆/ }));

    expect(screen.getByText('家父買進台積電')).toBeInTheDocument();
    expect(screen.queryByText('巴逆逆隨手發言沒喊單')).not.toBeInTheDocument();
    expect(screen.getByText('戰績排行榜')).toBeInTheDocument(); // still on scoreboard
  });

  it('只看喊單 toggle hides no-call posts', async () => {
    mockApi();
    renderAt('/');
    await screen.findByText('巴逆逆隨手發言沒喊單');
    await userEvent.click(screen.getByRole('button', { name: /只看喊單/ }));
    expect(screen.getByText('家父買進台積電')).toBeInTheDocument();
    expect(screen.queryByText('巴逆逆隨手發言沒喊單')).not.toBeInTheDocument();
  });

  it('renders the leaderboard + feed at /timeline', async () => {
    mockApi();
    renderAt('/timeline');
    expect(await screen.findByText('家父買進台積電')).toBeInTheDocument();
    // leaderboard cards show 命中率 label
    expect(screen.getAllByText('命中率').length).toBeGreaterThan(0);
  });

  it('redirects unknown paths to /', async () => {
    mockApi();
    renderAt('/nope');
    expect(await screen.findByText('戰績排行榜')).toBeInTheDocument();
  });
});
