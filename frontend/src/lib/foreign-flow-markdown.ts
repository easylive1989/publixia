import type {
  ForeignFuturesResponse,
  OptionsDetailRow,
  OptionsIdentity,
  OptionsPutCall,
} from '@/hooks/useForeignFutures';

const TARGET_DAYS = 5;

const IDENTITY_LABEL: Record<OptionsIdentity, string> = {
  foreign:          '外資',
  investment_trust: '投信',
  dealer:           '自營商',
};
const IDENTITY_ORDER: OptionsIdentity[] = ['foreign', 'investment_trust', 'dealer'];
const PUT_CALL_LABEL: Record<OptionsPutCall, string> = { CALL: '買權', PUT: '賣權' };
const PUT_CALL_ORDER: OptionsPutCall[] = ['CALL', 'PUT'];

const NA = '—';

function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || Number.isNaN(v)) return NA;
  return v.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtSigned(v: number | null | undefined, digits = 0): string {
  if (v == null || Number.isNaN(v)) return NA;
  const s = fmtNum(Math.abs(v), digits);
  if (v > 0) return '+' + s;
  if (v < 0) return '-' + s;
  return s;
}

/** TAIFEX 千元 → 億元 (÷100,000), 2 decimals */
function toBillions(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return NA;
  return (v / 100_000).toFixed(2);
}

const PROMPT_TEMPLATE = `> 你是個人交易者,擅長台指期短線技術分析。請根據以下最近交易日的外資期貨/選擇權/散戶多空比資料,產出:
> 1. 外資多空動向解讀(口數變化、成本變化、損益狀態)
> 2. TXO 選擇權三大法人布局解讀(買權/賣權、多/空)
> 3. 散戶多空比觀察(常用作反向指標)
> 4. 隔週(下週一~五)技術面交易計畫:看多/看空理由、進場區間、停損點、停利目標
> 5. 主要風險訊號與觀察重點`;

interface SliceResult {
  /** 視窗內各天的 index, 對應原 data.dates */
  indices: number[];
  dates: string[];
  startDate: string;
  endDate: string;
}

function sliceLastN(data: ForeignFuturesResponse, n: number): SliceResult {
  const total = data.dates.length;
  const take = Math.min(n, total);
  const start = total - take;
  const indices: number[] = [];
  for (let i = start; i < total; i++) indices.push(i);
  const dates = indices.map((i) => data.dates[i]);
  return {
    indices,
    dates,
    startDate: dates[0] ?? '',
    endDate: dates[dates.length - 1] ?? '',
  };
}

function dateLabel(date: string, settlementSet: Set<string>): string {
  return settlementSet.has(date) ? `${date} ✦` : date;
}

function buildKlineTable(data: ForeignFuturesResponse, slice: SliceResult, settlementSet: Set<string>): string {
  const lines: string[] = [];
  lines.push('## TX 期貨日線 (OHLCV)');
  lines.push('');
  lines.push('| 日期 | 開 | 高 | 低 | 收 | 量 |');
  lines.push('|---|---:|---:|---:|---:|---:|');
  for (const i of slice.indices) {
    const c = data.candles[i];
    lines.push(
      `| ${dateLabel(data.dates[i], settlementSet)} | ${fmtNum(c?.open)} | ${fmtNum(c?.high)} | ${fmtNum(c?.low)} | ${fmtNum(c?.close)} | ${fmtNum(c?.volume)} |`,
    );
  }
  lines.push('');
  lines.push('> ✦ 表示結算日');
  return lines.join('\n');
}

function buildForeignFuturesTable(data: ForeignFuturesResponse, slice: SliceResult): string {
  const lines: string[] = [];
  lines.push('## 外資期貨多空未平倉 (大台等值口)');
  lines.push('');
  lines.push('| 日期 | 淨口數 | 日變動 | 持倉成本 (點) | 未實現損益 (NTD) | 已實現損益 (NTD) |');
  lines.push('|---|---:|---:|---:|---:|---:|');
  for (const i of slice.indices) {
    lines.push(
      `| ${data.dates[i]} | ${fmtSigned(data.net_position[i])} | ${fmtSigned(data.net_change[i])} | ${fmtNum(data.cost[i], 0)} | ${fmtSigned(data.unrealized_pnl[i])} | ${fmtSigned(data.realized_pnl[i])} |`,
    );
  }
  lines.push('');
  lines.push('> 淨口數 = 多方未平倉 − 空方未平倉;持倉成本/未實現損益為近似值');
  return lines.join('\n');
}

function buildOptionsTable(data: ForeignFuturesResponse, slice: SliceResult): string | null {
  const opt = data.options;
  if (!opt) return null;

  const lines: string[] = [];
  lines.push('## TXO 選擇權三大法人未平倉 (口數 / 億元)');
  lines.push('');
  lines.push('| 日期 | 身份 | 買/賣 | 多方 OI | 空方 OI | 多方金額(億) | 空方金額(億) |');
  lines.push('|---|---|---|---:|---:|---:|---:|');

  let printed = 0;
  for (const i of slice.indices) {
    const date = data.dates[i];
    const rows = opt.detail_by_date[date];
    if (!rows || rows.length === 0) continue;
    const byKey = new Map<string, OptionsDetailRow>();
    for (const r of rows) byKey.set(`${r.identity}|${r.put_call}`, r);
    for (const id of IDENTITY_ORDER) {
      for (const pc of PUT_CALL_ORDER) {
        const r = byKey.get(`${id}|${pc}`);
        if (!r) continue;
        lines.push(
          `| ${date} | ${IDENTITY_LABEL[id]} | ${PUT_CALL_LABEL[pc]} | ${fmtNum(r.long_oi)} | ${fmtNum(r.short_oi)} | ${toBillions(r.long_amount)} | ${toBillions(r.short_amount)} |`,
        );
        printed++;
      }
    }
  }

  if (printed === 0) {
    lines.push('| — | — | — | — | — | — | — |');
    lines.push('');
    lines.push('> 此期間無 TXO 三大法人資料');
  } else {
    lines.push('');
    lines.push('> 金額單位為億元 (TAIFEX 千元 ÷ 100,000)');
  }
  return lines.join('\n');
}

function buildSpotTable(data: ForeignFuturesResponse, slice: SliceResult): string {
  const lines: string[] = [];
  lines.push('## 外資現貨淨買賣超 (TWSE 整體, 億元)');
  lines.push('');
  const hasAny = slice.indices.some((i) => data.foreign_spot_net[i] != null);
  if (!hasAny) {
    lines.push('> 此期間無外資現貨資料');
    return lines.join('\n');
  }
  lines.push('| 日期 | 外資現貨淨額 (億) |');
  lines.push('|---|---:|');
  for (const i of slice.indices) {
    lines.push(`| ${data.dates[i]} | ${fmtSigned(data.foreign_spot_net[i], 2)} |`);
  }
  lines.push('');
  lines.push('> 正值=外資現貨買超;負值=外資現貨賣超');
  return lines.join('\n');
}

function buildRetailTable(data: ForeignFuturesResponse, slice: SliceResult): string {
  const lines: string[] = [];
  lines.push('## 散戶多空比 (%)');
  lines.push('');
  const hasAny = slice.indices.some((i) => data.retail_ratio[i] != null);
  if (!hasAny) {
    lines.push('> 此期間無散戶多空比資料');
    return lines.join('\n');
  }
  lines.push('| 日期 | 散戶多空比 (%) |');
  lines.push('|---|---:|');
  for (const i of slice.indices) {
    const v = data.retail_ratio[i];
    const cell = v == null || Number.isNaN(v) ? NA : fmtSigned(v, 2);
    lines.push(`| ${data.dates[i]} | ${cell} |`);
  }
  lines.push('');
  lines.push('> 由 TAIFEX 大額交易人資料推算 (全市場 OI − 大戶 OI);常作為反向指標參考');
  return lines.join('\n');
}

export function buildForeignFlowMarkdown(
  data: ForeignFuturesResponse,
  downloadDate: string,
): string {
  const slice = sliceLastN(data, TARGET_DAYS);
  const settlementSet = new Set(data.settlement_dates);

  const header = [
    `# 台指期 · 外資動向 ${slice.indices.length} 日快照`,
    `資料期間: ${slice.startDate} ~ ${slice.endDate} (${slice.indices.length} 個交易日)`,
    `產出時間: ${downloadDate}`,
    '',
    '## AI 分析請求 (可直接複製給 ChatGPT/Claude)',
    '',
    PROMPT_TEMPLATE,
    '',
    '---',
    '',
  ].join('\n');

  const sections: string[] = [];
  sections.push(buildKlineTable(data, slice, settlementSet));
  sections.push(buildSpotTable(data, slice));
  sections.push(buildForeignFuturesTable(data, slice));
  const optionsTable = buildOptionsTable(data, slice);
  if (optionsTable) sections.push(optionsTable);
  sections.push(buildRetailTable(data, slice));

  return header + sections.join('\n\n') + '\n';
}

export function buildForeignFlowFilename(downloadDate: string): string {
  return `foreign-flow_${downloadDate}.md`;
}
