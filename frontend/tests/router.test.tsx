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

const peopleHandler = http.get('*/api/people', () =>
  HttpResponse.json({
    people: [
      {
        person_key: 'dadnini',
        display_name: '爸逆逆',
        avatar_url: null,
        platforms: ['threads'],
        latest_post_at: '2026-06-03T10:00:00',
        trade_count: 5,
      },
    ],
  }),
);

describe('routing', () => {
  it('renders HomePage with person cards at /', async () => {
    server.use(peopleHandler);
    renderAt('/');
    expect(await screen.findByText('爸逆逆')).toBeInTheDocument();
    expect(screen.getByText('追蹤名單')).toBeInTheDocument();
  });

  it('redirects unknown paths to /', async () => {
    server.use(peopleHandler);
    renderAt('/nonexistent/path');
    expect(await screen.findByText('爸逆逆')).toBeInTheDocument();
  });
});
