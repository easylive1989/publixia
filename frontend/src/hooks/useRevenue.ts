import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface RevenueRow {
  year: number;
  month: number;
  revenue: number | null;
  yoy_pct: number | null;
  ma12: number | null;
}

export interface RevenueResponse {
  ticker: string;
  months: number;
  ok: boolean;
  rows: RevenueRow[];
}

export function useRevenue(months = 36) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<RevenueResponse>({
    queryKey: ['stock-revenue', code, months],
    queryFn: () =>
      apiFetch<RevenueResponse>(
        `/api/stocks/${encodeURIComponent(code)}/revenue?months=${months}`,
      ),
    enabled: !!code,
  });
}
