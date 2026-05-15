import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export type GroupType = 'industry' | 'theme';

export interface SectorHeatmapGroup {
  code: string;
  name: string;
  latest_value: number;
  pct_series: Array<number | null>;
}

export interface SectorHeatmap {
  type: GroupType;
  days: string[];
  groups: SectorHeatmapGroup[];
}

export interface UseSectorHeatmapOptions {
  type?: GroupType;
  days?: number;
  topN?: number;
}

export function useSectorHeatmap(
  opts: UseSectorHeatmapOptions = {},
): UseQueryResult<SectorHeatmap> {
  const { type = 'industry', days = 5, topN = 10 } = opts;
  return useQuery<SectorHeatmap>({
    queryKey: ['sector-heatmap', type, days, topN],
    queryFn: () =>
      apiFetch<SectorHeatmap>(
        `/api/groups/heatmap?type=${type}&days=${days}&top_n=${topN}`,
      ),
    staleTime: 5 * 60 * 1000,
  });
}
