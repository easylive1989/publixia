import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import type { RangeKey } from '@/store/range-store';

export interface HistoryPoint {
  timestamp: string;
  value: number;
}

export function useIndicatorHistory(
  indicator: string,
  range: RangeKey,
): UseQueryResult<HistoryPoint[]> {
  return useQuery<HistoryPoint[]>({
    queryKey: ['indicator-history', indicator, range],
    queryFn: () =>
      apiFetch<HistoryPoint[]>(
        `/api/history/${encodeURIComponent(indicator)}?time_range=${range}`,
      ),
  });
}
