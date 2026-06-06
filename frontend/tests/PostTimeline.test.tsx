import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PostTimeline } from '../src/components/PostTimeline';
import type { Post } from '../src/hooks/usePeople';

function makePost(overrides: Partial<Post>): Post {
  return {
    id: 1,
    platform: 'threads',
    platform_post_id: 'P1',
    url: 'https://example/p1',
    content: '一般貼文內容',
    posted_at: '2026-06-03T10:00:00',
    extraction_status: 'done',
    title: null,
    trades: [],
    ...overrides,
  };
}

function renderTimeline(posts: Post[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PostTimeline posts={posts} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PostTimeline podcast rendering', () => {
  it('shows a Podcast badge, episode title and 聽這集 link for podcast posts', () => {
    renderTimeline([
      makePost({
        platform: 'podcast',
        title: '第 12 集：聊聊台積電',
        content: '這集我們深入討論半導體…',
      }),
    ]);
    expect(screen.getByText('Podcast')).toBeInTheDocument();
    expect(screen.getByText('第 12 集：聊聊台積電')).toBeInTheDocument();
    expect(screen.getByText(/聽這集/)).toBeInTheDocument();
  });

  it('shows 看原文 and no badge/title for threads posts', () => {
    renderTimeline([makePost({ platform: 'threads', title: null })]);
    expect(screen.queryByText('Podcast')).not.toBeInTheDocument();
    expect(screen.getByText(/看原文/)).toBeInTheDocument();
  });
});
