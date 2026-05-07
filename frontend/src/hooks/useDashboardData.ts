import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface IndicatorSlot {
  value: number;
  timestamp: string;
  extra: Record<string, unknown>;
  next_update_at?: string | null;
}

export type DashboardData = Record<string, IndicatorSlot>;

export function useDashboardData() {
  return useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: () => apiFetch<DashboardData>('/api/dashboard'),
  });
}
