import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface ForeignFuturesCandle {
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export type OptionsIdentity = 'foreign' | 'investment_trust' | 'dealer';
export type OptionsPutCall = 'CALL' | 'PUT';

export interface OptionsDetailRow {
  identity: OptionsIdentity;
  put_call: OptionsPutCall;
  long_oi: number;
  short_oi: number;
  /** 千元 (TAIFEX native unit; convert to 億元 at render time = ÷ 100,000) */
  long_amount: number;
  short_amount: number;
}

export interface OptionsBlock {
  /** TXO 外資 買權 多方未平倉契約金額 (千元), aligned with dates[] */
  foreign_call_long_amount: (number | null)[];
  foreign_call_short_amount: (number | null)[];
  foreign_put_long_amount: (number | null)[];
  foreign_put_short_amount: (number | null)[];
  /** Date → all rows for that date (3 identities × CALL/PUT). Dates
   *  with no TXO data are absent from this map. */
  detail_by_date: Record<string, OptionsDetailRow[]>;
}

export interface ForeignFuturesResponse {
  symbol: string;
  name: string;
  currency: string;
  time_range: string;
  dates: string[];
  candles: ForeignFuturesCandle[];
  /** 持倉成本 (point) — null when foreign net is flat */
  cost: (number | null)[];
  /** 多空未平倉口數淨額 (大台等值口) */
  net_position: (number | null)[];
  /** 日變動 (大台等值口) — null on first day */
  net_change: (number | null)[];
  /** 未實現損益 (NTD) — null when cost or close is missing */
  unrealized_pnl: (number | null)[];
  /** 已實現損益 (NTD) —近似算法 */
  realized_pnl: number[];
  /** 散戶多空比 (%) — null on days without 大額交易人 data */
  retail_ratio: (number | null)[];
  /** TWSE 整體外資現貨淨買賣超 (億元) — null on days without indicator data */
  foreign_spot_net: (number | null)[];
  /** 結算日 (YYYY-MM-DD) inside the visible window */
  settlement_dates: string[];
  /** TXO 三大法人選擇權買賣權分計 — 圖表序列以外資為主軸，
   *  明細表用 detail_by_date 呈現 3 身份 × CALL/PUT 完整資料 */
  options?: OptionsBlock;
}

export function useForeignFutures(
  range: string,
): UseQueryResult<ForeignFuturesResponse> {
  return useQuery<ForeignFuturesResponse>({
    queryKey: ['foreign-futures', 'tw', range],
    queryFn: () =>
      apiFetch<ForeignFuturesResponse>(
        `/api/futures/tw/foreign-flow?time_range=${encodeURIComponent(range)}`,
      ),
  });
}
