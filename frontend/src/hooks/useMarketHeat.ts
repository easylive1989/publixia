import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import type { HeatLevel } from '@/lib/market-heat';

export interface MarketHeatDay {
  date: string;               // ISO YYYY-MM-DD (交易日)
  taiex_close: number;
  turnover: number;           // 成交金額（億元）
  expected_turnover: number;  // 位階常態（億元）
  volume_ratio: number;       // turnover / expected
  residual: number;           // ln(volume_ratio)
  percentile: number;         // 近一年殘差百分位 0..1
  level: HeatLevel;
  label: string;              // 中文判讀（後端與 sheet 同字）
}

export interface MarketHeatPayload {
  latest: MarketHeatDay | null;
  days: MarketHeatDay[];      // date-ascending
}

export function useMarketHeat(days = 90) {
  return useQuery<MarketHeatPayload>({
    queryKey: ['market-heat', days],
    queryFn: () => apiFetch<MarketHeatPayload>(`/api/market/volume-heat?days=${days}`),
  });
}
