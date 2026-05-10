import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface ForeignFuturesCandle {
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface ForeignFuturesResponse {
  symbol: string;
  name: string;
  currency: string;
  time_range: string;
  dates: string[];
  candles: ForeignFuturesCandle[];
  /** 持倉成本 (point) — null when foreign net is flat */
  cost: (number | null)[];
  /** 多空未平倉口數淨額 (大台等值口) */
  net_position: (number | null)[];
  /** 日變動 (大台等值口) — null on first day */
  net_change: (number | null)[];
  /** 未實現損益 (NTD) — null when cost or close is missing */
  unrealized_pnl: (number | null)[];
  /** 已實現損益 (NTD) —近似算法 */
  realized_pnl: number[];
  /** 結算日 (YYYY-MM-DD) inside the visible window */
  settlement_dates: string[];
}

export function useForeignFutures(
  range: string,
): UseQueryResult<ForeignFuturesResponse> {
  return useQuery<ForeignFuturesResponse>({
    queryKey: ['foreign-futures', 'tw', range],
    queryFn: () =>
      apiFetch<ForeignFuturesResponse>(
        `/api/futures/tw/foreign-flow?time_range=${encodeURIComponent(range)}`,
      ),
  });
}
