import { describe, it, expect } from 'vitest';
import {
  buildForeignFlowFilename,
  buildForeignFlowMarkdown,
} from '../src/lib/foreign-flow-markdown';
import type { ForeignFuturesResponse } from '../src/hooks/useForeignFutures';

function makeData(overrides: Partial<ForeignFuturesResponse> = {}): ForeignFuturesResponse {
  const dates = ['2026-05-05', '2026-05-06', '2026-05-07', '2026-05-08', '2026-05-09'];
  const base: ForeignFuturesResponse = {
    symbol: 'TX',
    name: 'TX 外資動向',
    currency: 'TWD',
    time_range: '1M',
    dates,
    candles: dates.map((_, i) => ({
      open:   17000 + i * 10,
      high:   17050 + i * 10,
      low:    16950 + i * 10,
      close:  17020 + i * 10,
      volume: 12345 + i,
    })),
    cost:           [17_000, 17_010, 17_020, 17_030, 17_040],
    net_position:   [1000, 1100, 900, -200, 500],
    net_change:     [null, 100, -200, -1100, 700],
    unrealized_pnl: [50000, 60000, -30000, -200000, 80000],
    realized_pnl:   [0, 1000, -2000, 3000, -4000],
    retail_ratio:   [-5.2, -4.1, 3.0, 0, -2.5],
    settlement_dates: ['2026-05-07'],
    options: {
      foreign_call_long_amount:  dates.map(() => 2_488_000),
      foreign_call_short_amount: dates.map(() => 2_345_000),
      foreign_put_long_amount:   dates.map(() => 247_000),
      foreign_put_short_amount:  dates.map(() => 166_000),
      detail_by_date: Object.fromEntries(
        dates.map((d) => [
          d,
          [
            { identity: 'foreign' as const,          put_call: 'CALL' as const,
              long_oi: 12862, short_oi: 11092, long_amount: 2_488_000, short_amount: 2_345_000 },
            { identity: 'foreign' as const,          put_call: 'PUT'  as const,
              long_oi: 18494, short_oi: 14943, long_amount: 247_000,   short_amount: 166_000 },
            { identity: 'investment_trust' as const, put_call: 'CALL' as const,
              long_oi: 1,     short_oi: 430,   long_amount: 0,         short_amount: 150_000 },
            { identity: 'investment_trust' as const, put_call: 'PUT'  as const,
              long_oi: 127,   short_oi: 0,     long_amount: 0,         short_amount: 0 },
            { identity: 'dealer' as const,           put_call: 'CALL' as const,
              long_oi: 18680, short_oi: 16884, long_amount: 2_940_000, short_amount: 3_104_000 },
            { identity: 'dealer' as const,           put_call: 'PUT'  as const,
              long_oi: 34609, short_oi: 29268, long_amount: 278_000,   short_amount: 349_000 },
          ],
        ]),
      ),
    },
  };
  return { ...base, ...overrides };
}

describe('buildForeignFlowFilename', () => {
  it('uses foreign-flow_<date>.md pattern', () => {
    expect(buildForeignFlowFilename('2026-05-11')).toBe('foreign-flow_2026-05-11.md');
  });
});

describe('buildForeignFlowMarkdown', () => {
  it('renders header with correct date range and 5 trading days', () => {
    const md = buildForeignFlowMarkdown(makeData(), '2026-05-11');
    expect(md).toContain('# 台指期 · 外資動向 5 日快照');
    expect(md).toContain('資料期間: 2026-05-05 ~ 2026-05-09 (5 個交易日)');
    expect(md).toContain('產出時間: 2026-05-11');
  });

  it('includes the AI prompt template up front', () => {
    const md = buildForeignFlowMarkdown(makeData(), '2026-05-11');
    expect(md).toContain('## AI 分析請求');
    expect(md).toContain('你是個人交易者');
    expect(md).toContain('隔週(下週一~五)技術面交易計畫');
  });

  it('renders K-line table rows for all 5 days', () => {
    const md = buildForeignFlowMarkdown(makeData(), '2026-05-11');
    expect(md).toContain('## TX 期貨日線 (OHLCV)');
    expect(md).toMatch(/\| 2026-05-05 \| 17,000 \| 17,050 \| 16,950 \| 17,020 \| 12,345 \|/);
    expect(md).toMatch(/\| 2026-05-09 \|/);
  });

  it('marks settlement dates with ✦', () => {
    const md = buildForeignFlowMarkdown(makeData(), '2026-05-11');
    expect(md).toContain('| 2026-05-07 ✦ |');
  });

  it('renders foreign futures table with signed values and net_change null on first day', () => {
    const md = buildForeignFlowMarkdown(makeData(), '2026-05-11');
    expect(md).toContain('## 外資期貨多空未平倉 (大台等值口)');
    // Day 1 net_change is null → —
    expect(md).toMatch(/\| 2026-05-05 \| \+1,000 \| — \| 17,000 \| \+50,000 \| 0 \|/);
    // Day 4 net_position negative → -200
    expect(md).toMatch(/\| 2026-05-08 \| -200 \| -1,100 \| 17,030 \| -200,000 \| \+3,000 \|/);
  });

  it('converts TXO amount from 千元 to 億元 (2,488,000 → 24.88)', () => {
    const md = buildForeignFlowMarkdown(makeData(), '2026-05-11');
    expect(md).toContain('## TXO 選擇權三大法人未平倉');
    expect(md).toContain('| 外資 | 買權 |');
    // Foreign CALL: long 2,488,000 → 24.88, short 2,345,000 → 23.45
    expect(md).toMatch(/\| 外資 \| 買權 \| 12,862 \| 11,092 \| 24\.88 \| 23\.45 \|/);
    // Dealer PUT: long 278,000 → 2.78, short 349,000 → 3.49
    expect(md).toMatch(/\| 自營商 \| 賣權 \| 34,609 \| 29,268 \| 2\.78 \| 3\.49 \|/);
  });

  it('skips TXO section content when options block missing', () => {
    const data = makeData();
    delete data.options;
    const md = buildForeignFlowMarkdown(data, '2026-05-11');
    expect(md).not.toContain('## TXO 選擇權三大法人未平倉');
  });

  it('shows retail ratio table with signed percentages', () => {
    const md = buildForeignFlowMarkdown(makeData(), '2026-05-11');
    expect(md).toContain('## 散戶多空比 (%)');
    expect(md).toContain('| 2026-05-05 | -5.20 |');
    expect(md).toContain('| 2026-05-08 | 0.00 |');
  });

  it('shows fallback message when retail_ratio is all null', () => {
    const data = makeData({ retail_ratio: [null, null, null, null, null] });
    const md = buildForeignFlowMarkdown(data, '2026-05-11');
    expect(md).toContain('## 散戶多空比');
    expect(md).toContain('此期間無散戶多空比資料');
    // Should not render the table header in this case
    expect(md).not.toMatch(/\| 日期 \| 散戶多空比 \(%\) \|/);
  });

  it('renders fewer rows when data has less than 5 days', () => {
    const data = makeData();
    const cut = 3;
    data.dates = data.dates.slice(0, cut);
    data.candles = data.candles.slice(0, cut);
    data.cost = data.cost.slice(0, cut);
    data.net_position = data.net_position.slice(0, cut);
    data.net_change = data.net_change.slice(0, cut);
    data.unrealized_pnl = data.unrealized_pnl.slice(0, cut);
    data.realized_pnl = data.realized_pnl.slice(0, cut);
    data.retail_ratio = data.retail_ratio.slice(0, cut);

    const md = buildForeignFlowMarkdown(data, '2026-05-11');
    expect(md).toContain('# 台指期 · 外資動向 3 日快照');
    expect(md).toContain('資料期間: 2026-05-05 ~ 2026-05-07 (3 個交易日)');
    // 5-th day not included
    expect(md).not.toContain('| 2026-05-09 |');
    // 3-rd day included
    expect(md).toContain('| 2026-05-07 ✦ |');
  });

  it('handles null derived metrics gracefully', () => {
    const data = makeData({
      cost:           [null, null, null, null, null],
      net_position:   [null, null, null, null, null],
      unrealized_pnl: [null, null, null, null, null],
    });
    const md = buildForeignFlowMarkdown(data, '2026-05-11');
    expect(md).toMatch(/\| 2026-05-05 \| — \| — \| — \| — \| 0 \|/);
  });

  it('handles dates with no TXO detail rows by omitting them from the table', () => {
    const data = makeData();
    // Keep options block but blank out detail_by_date
    data.options!.detail_by_date = {};
    const md = buildForeignFlowMarkdown(data, '2026-05-11');
    expect(md).toContain('## TXO 選擇權三大法人未平倉');
    expect(md).toContain('此期間無 TXO 三大法人資料');
  });
});
