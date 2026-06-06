import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

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
  // price tracking from the post's entry time (null until computed/elapsed)
  pct_latest: number | null;  // current price vs entry
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
  title: string | null;  // episode title for podcasts; null for text platforms
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

export interface Standing {
  person_key: string;
  display_name: string;
  win_count: number;
  loss_count: number;
  signal_count: number;
  win_rate: number | null;   // 0..1
  cum_return: number | null; // fraction sum, e.g. -0.342
  form: ('w' | 'l')[];       // newest first, up to 5
  dnp: boolean;              // no evaluated call
  rank: number | null;
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

export function useScoreboard() {
  return useQuery<Standing[]>({
    queryKey: [...PEOPLE_KEY, 'scoreboard'],
    queryFn: async () => {
      const data = await apiFetch<{ standings: Standing[] }>('/api/scoreboard');
      return data.standings;
    },
  });
}
