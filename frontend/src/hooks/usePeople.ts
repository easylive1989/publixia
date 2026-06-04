import { useQuery } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api-client';

export type Direction = 'buy' | 'sell' | 'hold' | 'bullish' | 'bearish';

export interface Trade {
  raw_symbol: string;
  ticker: string | null;
  market: string | null;
  stock_name: string | null;
  direction: Direction;
  price: number | null;
  quantity: number | null;
  trade_date: string | null;
  confidence: number;
  // price tracking from the post's entry time (null until the window elapses)
  pct_7d: number | null;
  pct_1m: number | null;
  base_price: number | null;
  price_status: string | null;
}

export interface Post {
  id: number;
  platform: string;
  platform_post_id: string;
  url: string;
  content: string;
  posted_at: string | null;
  extraction_status: string;
  trades: Trade[];
}

export interface PostAuthor {
  person_key: string;
  display_name: string;
  avatar_url: string | null;
}

export interface TimelinePost extends Post {
  person: PostAuthor;
}

export interface PersonSummary {
  person_key: string;
  display_name: string;
  avatar_url: string | null;
  platforms: string[];
  latest_post_at: string | null;
  trade_count: number;
}

export interface PersonAccount {
  platform: string;
  handle: string;
  profile_url: string;
}

export interface PersonProfile {
  person_key: string;
  display_name: string;
  avatar_url: string | null;
  accounts: PersonAccount[];
}

export const PEOPLE_KEY = ['people'] as const;

export function usePeople() {
  return useQuery<PersonSummary[]>({
    queryKey: PEOPLE_KEY,
    queryFn: async () => {
      const data = await apiFetch<{ people: PersonSummary[] }>('/api/people');
      return data.people;
    },
  });
}

export function useTimeline(limit = 60) {
  return useQuery<TimelinePost[]>({
    queryKey: [...PEOPLE_KEY, 'timeline', limit],
    queryFn: async () => {
      const data = await apiFetch<{ posts: TimelinePost[] }>(`/api/timeline?limit=${limit}`);
      return data.posts;
    },
  });
}

export function usePersonProfile(personKey: string) {
  return useQuery<PersonProfile | null>({
    queryKey: [...PEOPLE_KEY, personKey],
    queryFn: async () => {
      try {
        return await apiFetch<PersonProfile>(`/api/people/${personKey}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
  });
}

export function usePersonPosts(personKey: string, limit = 50) {
  return useQuery<Post[]>({
    queryKey: [...PEOPLE_KEY, personKey, 'posts', limit],
    queryFn: async () => {
      const data = await apiFetch<{ posts: Post[] }>(
        `/api/people/${personKey}/posts?limit=${limit}`,
      );
      return data.posts;
    },
  });
}
