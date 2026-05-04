import type { AlertRecord } from '@/hooks/useAlerts';

export const INDICATOR_LABELS: Record<string, string> = {
  taiex: '加權指數',
  fx: '台幣兌美金',
  fear_greed: '恐懼貪婪指數',
  margin_balance: '融資餘額',
  short_balance: '融券餘額',
  short_margin_ratio: '券資比',
  total_foreign_net: '外資淨買超',
  total_trust_net: '投信淨買超',
  total_dealer_net: '自營商淨買超',
  ndc: '國發會景氣指標',
  tw_volume: '台股成交金額',
  us_volume: '美股 S&P500 成交量',
};

export const STOCK_INDICATOR_LABELS: Record<string, string> = {
  per: 'PER',
  pbr: 'PBR',
  dividend_yield: '殖利率',
  foreign_net: '外資淨買',
  trust_net: '投信淨買',
  dealer_net: '自營淨買',
  margin_balance: '融資餘額',
  short_balance: '融券餘額',
  revenue: '月營收',
  q_eps: '季 EPS',
  q_revenue: '季營收',
  q_operating_income: '季營業利益',
  q_net_income: '季稅後淨利',
  q_operating_cf: '季營業 CF',
  y_cash_dividend: '年現金股利',
  y_stock_dividend: '年股票股利',
};

export function alertTargetLabel(a: AlertRecord): string {
  if (a.target_type === 'indicator') {
    return INDICATOR_LABELS[a.target] ?? a.target;
  }
  if (a.target_type === 'stock_indicator') {
    const ik = a.indicator_key ?? '';
    return `${a.target} ${STOCK_INDICATOR_LABELS[ik] ?? ik}`.trim();
  }
  return a.target;
}

export function conditionLabel(a: AlertRecord): string {
  switch (a.condition) {
    case 'above': return '≥';
    case 'below': return '≤';
    case 'streak_above': return `連 ${a.window_n} 日 ≥`;
    case 'streak_below': return `連 ${a.window_n} 日 ≤`;
    case 'percentile_above': return '5y 百分位 ≥';
    case 'percentile_below': return '5y 百分位 ≤';
    case 'yoy_above': return 'YoY ≥';
    case 'yoy_below': return 'YoY ≤';
    default: return a.condition;
  }
}

export function thresholdPlaceholder(condition: string): string {
  if (condition.startsWith('percentile_')) return '百分位 0–100';
  if (condition.startsWith('yoy_')) return 'YoY %（可正可負）';
  return '門檻數值';
}
