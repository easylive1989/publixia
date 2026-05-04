import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface WatchlistRow {
  ticker: string;
  name: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  currency: string | null;
  timestamp: string | null;
}

export function useWatchlist() {
  return useQuery<WatchlistRow[]>({
    queryKey: ['stocks'],
    queryFn: () => apiFetch<WatchlistRow[]>('/api/stocks'),
  });
}

export function useAddStock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) =>
      apiFetch('/api/stocks', { method: 'POST', body: JSON.stringify({ ticker }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['stocks'] }),
  });
}

export function useDeleteStock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) =>
      apiFetch(`/api/stocks/${encodeURIComponent(ticker)}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['stocks'] }),
  });
}
