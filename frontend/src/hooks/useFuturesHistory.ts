import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import type { StockHistoryResponse } from '@/hooks/useStockHistory';

export interface FuturesHistoryResponse extends Omit<StockHistoryResponse, 'ticker'> {
  symbol: string;
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
