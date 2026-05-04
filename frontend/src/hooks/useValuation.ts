import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface ValuationRow {
  date: string;
  per: number | null;
  pbr: number | null;
  dividend_yield: number | null;
}

export interface ValuationLatest {
  per: number | null;
  pbr: number | null;
  dividend_yield: number | null;
  per_percentile_5y: number | null;
}

export interface ValuationRange {
  min: number | null;
  max: number | null;
  avg: number | null;
}

export interface ValuationRange5y {
  per: ValuationRange;
  pbr: ValuationRange;
  dividend_yield: ValuationRange;
}

export interface ValuationResponse {
  ticker: string;
  years: number;
  as_of: string | null;
  ok: boolean;
  latest: ValuationLatest;
  range_5y: ValuationRange5y;
  rows: ValuationRow[];
}

export function useValuation(years = 5) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<ValuationResponse>({
    queryKey: ['stock-valuation', code, years],
    queryFn: () =>
      apiFetch<ValuationResponse>(
        `/api/stocks/${encodeURIComponent(code)}/valuation?years=${years}`,
      ),
    enabled: !!code,
  });
}
