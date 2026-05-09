import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/NewsCard';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const spec = listCards('dashboard').find((c) => c.id === 'news')!;
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Card />
    </QueryClientProvider>,
  );
}

describe('NewsCard', () => {
  it('registers as a narrow (cols=1) dashboard card', () => {
    const spec = listCards('dashboard').find((c) => c.id === 'news');
    expect(spec?.cols).toBe(1);
  });

  it('renders items as external anchor tags', async () => {
    server.use(
      http.get('*/api/news', () =>
        HttpResponse.json([
          {
            title: 'A 公司營收創高',
            url: 'https://news.example/a',
            source: '鉅亨網台股',
            published: new Date().toISOString(),
          },
          {
            title: 'B 央行升息',
            url: 'https://news.example/b',
            source: '鉅亨頭條',
            published: new Date().toISOString(),
          },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      const a = screen.getByRole('link', { name: 'A 公司營收創高' });
      expect(a).toHaveAttribute('href', 'https://news.example/a');
      expect(a).toHaveAttribute('target', '_blank');
    });
  });
});
