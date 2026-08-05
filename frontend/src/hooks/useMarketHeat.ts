import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import type { HeatLevel } from '@/lib/market-heat';
import type { MarketId } from '@/lib/markets';

export interface MarketHeatDay {
  date: string;               // ISO YYYY-MM-DD (交易日)
  index_close: number;        // 指數收盤（TW 加權 / US Nasdaq Composite）
  turnover: number;           // 量能（TW 成交金額億元 / US 成交股數億股）
  expected_turnover: number;  // 位階常態（同 turnover 單位）
  volume_ratio: number;       // turnover / expected
  residual: number;           // ln(volume_ratio)
  percentile: number;         // 近一年殘差百分位 0..1
  level: HeatLevel;
  label: string;              // 中文判讀（後端與 sheet 同字）
}

export interface MarketHeatPayload {
  market: MarketId;
  latest: MarketHeatDay | null;
  days: MarketHeatDay[];      // date-ascending
}

/** ``days = null`` 抓該市場的全歷史（2016 起）。 */
export function useMarketHeat(days: number | null, market: MarketId) {
  return useQuery<MarketHeatPayload>({
    queryKey: ['market-heat', market, days ?? 'all'],
    queryFn: () => {
      const params = new URLSearchParams({ market });
      if (days) params.set('days', String(days));
      return apiFetch<MarketHeatPayload>(`/api/market/volume-heat?${params}`);
    },
  });
}
