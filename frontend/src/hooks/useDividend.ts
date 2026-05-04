import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface DividendYear {
  year: number;
  cash_dividend: number | null;
  stock_dividend: number | null;
  payout_ratio_pct: number | null;
  dividend_yield_pct: number | null;
}

export interface DividendResponse {
  ticker: string;
  years: number;
  ok: boolean;
  rows: DividendYear[];
}

export function useDividend(years = 10) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<DividendResponse>({
    queryKey: ['stock-dividend', code, years],
    queryFn: () =>
      apiFetch<DividendResponse>(
        `/api/stocks/${encodeURIComponent(code)}/dividend?years=${years}`,
      ),
    enabled: !!code,
  });
}
