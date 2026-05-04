import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface Candle {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StockHistoryResponse {
  ticker: string;
  name: string;
  currency: string;
  time_range: string;
  dates: string[];
  candles: Candle[];
  indicators: {
    ma5: (number | null)[];
    ma20: (number | null)[];
    ma60: (number | null)[];
    rsi14: (number | null)[];
    macd: (number | null)[];
    macd_signal: (number | null)[];
    macd_histogram: (number | null)[];
  };
}

export function useStockHistory(): UseQueryResult<StockHistoryResponse> {
  const { code = '' } = useParams<{ code: string }>();
  const [params] = useSearchParams();
  const range = params.get('range') || '3M';
  return useQuery<StockHistoryResponse>({
    queryKey: ['stock-history', code, range],
    queryFn: () =>
      apiFetch<StockHistoryResponse>(
        `/api/stocks/${encodeURIComponent(code)}/history?time_range=${range}`,
      ),
    enabled: !!code,
  });
}
