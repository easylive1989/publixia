import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface ChipRow {
  date: string;
  foreign_net: number | null;
  trust_net: number | null;
  dealer_net: number | null;
  margin_balance: number | null;
  short_balance: number | null;
}

export interface ChipResponse {
  ticker: string;
  days: number;
  ok: boolean;
  rows: ChipRow[];
}

export function useChip(days = 20) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<ChipResponse>({
    queryKey: ['stock-chip', code, days],
    queryFn: () =>
      apiFetch<ChipResponse>(`/api/stocks/${encodeURIComponent(code)}/chip?days=${days}`),
    enabled: !!code,
  });
}
