export type MarketId = 'TW';

export interface MarketConfig {
  id: MarketId;
  /** 指數的稱呼（卡片 / 表頭 / tooltip） */
  indexLabel: string;
  /** 量能的稱呼 */
  volumeLabel: string;
  /** 量能單位，接在數字後（「3,214 億」/「62 億股」） */
  unit: string;
  /** 表頭用的括號單位（「成交金額(億元)」/「成交股數(億股)」） */
  columnUnit: string;
  /** 資料回補起點，決定半年區間選單列到哪一年 */
  dataStartYear: number;
}

export const MARKETS: MarketConfig[] = [
  {
    id: 'TW',
    indexLabel: '加權指數',
    volumeLabel: '成交金額',
    unit: '億',
    columnUnit: '億元',
    dataStartYear: 2016,
  },
];

export const DEFAULT_MARKET = MARKETS[0];

export function marketById(id: string): MarketConfig {
  return MARKETS.find((m) => m.id === id) ?? DEFAULT_MARKET;
}
