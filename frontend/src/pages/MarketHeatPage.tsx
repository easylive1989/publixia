import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { HeatTable } from '@/components/HeatTable';
import { InstitutionalFlowPanel } from '@/components/InstitutionalFlow';
import { IndexChart, IndexLegend } from '@/components/IndexChart';
import { MarketHeat } from '@/components/MarketHeat';
import { SentimentTable } from '@/components/SentimentTable';
import { useMarketHeat } from '@/hooks/useMarketHeat';
import {
  filterHalfYear,
  halfYearLabel,
  halfYearOptions,
  halfYearValue,
  parseHalfYear,
  type HalfYear,
} from '@/lib/half-year';
import { DEFAULT_MARKET } from '@/lib/markets';

// 區間以交易日計：一月 ~22、一季 ~66、半年 ~130、一年 ~240。
const RANGES: { label: string; days: number | null }[] = [
  { label: '近一月', days: 22 },
  { label: '近一季', days: 66 },
  { label: '近半年', days: 130 },
  { label: '近一年', days: 240 },
  { label: '全部', days: null },
];

export default function MarketHeatPage() {
  const market = DEFAULT_MARKET;
  const [days, setDays] = useState<number | null>(66);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  // 選了半年區間就改抓全歷史，再於前端切出該半年；此時區間 tab 不亮。
  const [half, setHalf] = useState<HalfYear | null>(null);
  const heat = useMarketHeat(half ? null : days, market.id);
  const all = heat.data?.days ?? [];
  const rows = half ? filterHalfYear(all, half) : all;
  const selected = rows.find((row) => row.date === selectedDate) ?? rows[rows.length - 1] ?? null;
  // 選取日期不在新區間時回到該區間最新日；仍在範圍內則保留使用者選擇。
  useEffect(() => {
    if (rows.length && !rows.some((row) => row.date === selectedDate)) {
      setSelectedDate(rows[rows.length - 1].date);
    }
  }, [rows, selectedDate]);
  const shown = { market: market.id, latest: selected, days: rows };
  const options = halfYearOptions(heat.data?.latest?.date, market.dataStartYear);

  return (
    <main className="wrap">
      <div className="toolbar">
        <div className="range-picker">
          <div className="filters" role="tablist" aria-label="區間">
            {RANGES.map((r) => (
              <button
                key={r.label}
                role="tab"
                aria-selected={!half && days === r.days}
                className={`tab${!half && days === r.days ? ' on' : ''}`}
                onClick={() => {
                  setHalf(null);
                  setDays(r.days);
                }}
              >
                {r.label}
              </button>
            ))}
          </div>
          <select
            className={`half-select${half ? ' on' : ''}`}
            aria-label="半年區間"
            value={half ? halfYearValue(half) : ''}
            onChange={(e) => setHalf(parseHalfYear(e.target.value))}
          >
            <option value="">半年區間…</option>
            {options.map((h) => (
              <option key={halfYearValue(h)} value={halfYearValue(h)}>
                {halfYearLabel(h)}半年
              </option>
            ))}
          </select>
        </div>
        <Link className="method-link" to="/method">計算原理</Link>
      </div>

      {half && !heat.isLoading && rows.length === 0 ? (
        <div className="empty-note">{halfYearLabel(half)}半年沒有資料。</div>
      ) : (
        <MarketHeat data={shown} isLoading={heat.isLoading} market={market} />
      )}

      {selected && (
        <InstitutionalFlowPanel
          day={selected}
          rows={rows}
          onSelectDate={setSelectedDate}
        />
      )}

      {rows.length > 0 && (
        <section className="panel idx-panel">
          <div className="idx-panel-head">
            <h2 className="panel-title">{market.indexLabel} vs 三大法人買賣</h2>
            <span>點選任一交易日，同步切換上方量能與法人資料</span>
          </div>
          <IndexChart
            days={rows}
            market={market}
            selectedDate={selected?.date ?? rows[rows.length - 1].date}
            onSelectDate={setSelectedDate}
          />
          <IndexLegend market={market} />
        </section>
      )}

      <SentimentTable rows={rows} market={market} />

      <HeatTable rows={rows} market={market} />
    </main>
  );
}
