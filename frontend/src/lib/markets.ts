// 冷熱判讀支援的市場。
//
// 判讀模型本身跟市場無關 —— 它只吃「指數收盤 + 當日量能」，每個市場各自用
// 自己的歷史迴歸、自己的近一年分佈排百分位，不跨市場比較。所以這裡放的純粹
// 是「同一個數字在各市場叫什麼、單位是什麼」。
//
// 兩邊的量能不是同一種東西：台股存成交金額（億元），Nasdaq 存成交股數
// （億股，composite volume）。詳見 /method 的說明。

export type MarketId = 'TW' | 'US';

export interface MarketConfig {
  id: MarketId;
  /** 分頁名 */
  tab: string;
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
    tab: '台股大盤',
    indexLabel: '加權指數',
    volumeLabel: '成交金額',
    unit: '億',
    columnUnit: '億元',
    dataStartYear: 2016,
  },
  {
    id: 'US',
    tab: 'Nasdaq',
    indexLabel: 'Nasdaq 指數',
    volumeLabel: '成交股數',
    unit: '億股',
    columnUnit: '億股',
    dataStartYear: 2016,
  },
];

export const DEFAULT_MARKET = MARKETS[0];

export function marketById(id: string): MarketConfig {
  return MARKETS.find((m) => m.id === id) ?? DEFAULT_MARKET;
}
