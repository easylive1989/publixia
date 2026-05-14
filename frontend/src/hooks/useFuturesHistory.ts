import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import type { OhlcvSeries } from '@/lib/flatten-history';

export interface FuturesHistoryResponse extends Omit<OhlcvSeries, 'ticker'> {
  symbol:     string;
  name:       string;
  currency:   string;
  time_range: string;
}

export function useFuturesHistory(range: string): UseQueryResult<FuturesHistoryResponse> {
  return useQuery<FuturesHistoryResponse>({
    queryKey: ['futures-history', 'tw', range],
    queryFn: () =>
      apiFetch<FuturesHistoryResponse>(
        `/api/futures/tw/history?time_range=${encodeURIComponent(range)}`,
      ),
  });
}
