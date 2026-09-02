import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import type { HeatLevel } from '@/lib/market-heat';
import type { MarketId } from '@/lib/markets';

export interface InstitutionalAmount {
  buy: number;   // 億元
  sell: number;  // 億元
  net: number;   // buy - sell，億元
}

export interface InstitutionalFlow {
  date: string;
  dealer_proprietary: InstitutionalAmount;
  dealer_hedge: InstitutionalAmount;
  dealer: InstitutionalAmount;
  trust: InstitutionalAmount;
  foreign: InstitutionalAmount;
  foreign_dealer: InstitutionalAmount;
  total: InstitutionalAmount;
  turnover_ratio: number | null; // (法人買+賣)/(市場成交金額*2)，百分比
}

export interface MarketHeatDay {
  date: string;               // ISO YYYY-MM-DD (交易日)
  index_close: number;        // 台股加權指數收盤
  turnover: number;           // 台股成交金額（億元）
  expected_turnover: number;  // 位階常態（同 turnover 單位）
  volume_ratio: number;       // turnover / expected
  residual: number;           // ln(volume_ratio)
  percentile: number;         // 近一年殘差百分位 0..1
  level: HeatLevel;
  label: string;              // 中文判讀（後端與 sheet 同字）
  institutional?: InstitutionalFlow | null;
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
