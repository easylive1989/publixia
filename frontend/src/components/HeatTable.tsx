import type { MarketHeatDay } from '@/hooks/useMarketHeat';
import { HEAT_META, fmtBillion } from '@/lib/market-heat';
import type { MarketConfig } from '@/lib/markets';

/** Google Sheet 原始比較表：同欄位、同判讀字，最新在上。 */
export function HeatTable({ rows, market }: { rows: MarketHeatDay[]; market: MarketConfig }) {
  if (rows.length === 0) return null;
  const desc = [...rows].reverse();
  return (
    <div className="sheet-wrap">
      <table className="sheet">
        <thead>
          <tr>
            <th>日期</th>
            <th>{market.indexLabel}</th>
            <th>{market.volumeLabel}({market.columnUnit})</th>
            <th>位階常態({market.columnUnit})</th>
            <th>量能比</th>
            <th>殘差</th>
            <th>近一年百分位</th>
            <th>判讀</th>
          </tr>
        </thead>
        <tbody>
          {desc.map((d) => {
            const meta = HEAT_META[d.level];
            return (
              <tr key={d.date}>
                <td className="mono">{d.date}</td>
                <td className="mono">{d.index_close.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                <td className="mono">{fmtBillion(d.turnover)}</td>
                <td className="mono">{fmtBillion(d.expected_turnover)}</td>
                <td className="mono">{d.volume_ratio.toFixed(2)}</td>
                <td className="mono">{d.residual.toFixed(3)}</td>
                <td className="mono">{d.percentile.toFixed(3)}</td>
                <td>
                  <span
                    className="sheet-verdict"
                    style={{ background: meta.color, color: meta.darkText ? 'var(--ink)' : '#fff' }}
                  >
                    {d.label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
