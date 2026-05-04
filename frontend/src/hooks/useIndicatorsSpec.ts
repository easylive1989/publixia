import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface IndicatorSpec {
  key: string;
  label: string;
  unit: string | null;
  supported_conditions: string[];
}

export interface IndicatorsSpec {
  indicator: IndicatorSpec[];
  stock_indicator: IndicatorSpec[];
}

export function useIndicatorsSpec() {
  return useQuery<IndicatorsSpec>({
    queryKey: ['indicators-spec'],
    queryFn: () => apiFetch<IndicatorsSpec>('/api/indicators/spec'),
    staleTime: Infinity,
  });
}
