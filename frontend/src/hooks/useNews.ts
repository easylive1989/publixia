import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface NewsItem {
  title: string;
  url: string;
  source: string;
  published: string;
}

export function useNews(limit = 15) {
  return useQuery<NewsItem[]>({
    queryKey: ['news', limit],
    queryFn: () => apiFetch<NewsItem[]>(`/api/news?limit=${limit}`),
  });
}
