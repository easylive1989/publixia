import type { InstitutionalAmount, MarketHeatDay } from '@/hooks/useMarketHeat';

const GROUPS = [
  { key: 'foreign' as const, label: '外資', color: 'var(--inst-foreign)' },
  { key: 'dealer' as const, label: '自營商', color: 'var(--inst-dealer)' },
  { key: 'trust' as const, label: '投信', color: 'var(--inst-trust)' },
];

function fmtAmount(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
function fmtNet(value: number): string {
  if (Math.abs(value) < 0.005) return '0.00';
  return `${value > 0 ? '+' : ''}${fmtAmount(value)}`;
}

function netClass(value: number): string {
  if (value > 0.005) return 'inst-net buy';
  if (value < -0.005) return 'inst-net sell';
  return 'inst-net flat';
}

function rocDate(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  const weekday = new Date(year, month - 1, day, 12).getDay();
  const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
  return `${year - 1911}.${String(month).padStart(2, '0')}.${String(day).padStart(2, '0')}（${weekdays[weekday]}）`;
}

function AmountRow({ label, amount, sub = false }: {
  label: string;
  amount: InstitutionalAmount;
  sub?: boolean;
}) {
  return (
    <tr>
      <td className={sub ? 'inst-sub' : undefined}>{label}</td>
      <td className="mono">{fmtAmount(amount.buy)}</td>
      <td className="mono">{fmtAmount(amount.sell)}</td>
      <td className={`mono ${netClass(amount.net)}`}>{fmtNet(amount.net)}</td>
    </tr>
  );
}

export function InstitutionalFlowPanel({
  day,
  rows,
  onSelectDate,
}: {
  day: MarketHeatDay;
  rows: MarketHeatDay[];
  onSelectDate: (date: string) => void;
}) {
  const index = rows.findIndex((row) => row.date === day.date);
  const flow = day.institutional;
  const move = (offset: number) => {
    const target = rows[index + offset];
    if (target) onSelectDate(target.date);
  };

  return (
    <section className="inst-panel" aria-labelledby="inst-title">
      <header className="inst-head">
        <div className="inst-title-wrap">
          <h2 id="inst-title">三大法人買賣</h2>
          <span>INSTITUTIONAL FLOW · 收盤</span>
        </div>
        <div className="inst-date-control" aria-label="法人資料日期">
          <button
            type="button"
            aria-label="前一個交易日"
            disabled={index <= 0}
            onClick={() => move(-1)}
          >‹</button>
          <time className="mono" dateTime={day.date}>{rocDate(day.date)}</time>
          <button
            type="button"
            aria-label="後一個交易日"
            disabled={index < 0 || index >= rows.length - 1}
            onClick={() => move(1)}
          >›</button>
        </div>
      </header>

      {!flow ? (
        <div className="inst-empty">
          這個交易日的法人資料尚未同步；近期資料會優先回補。
        </div>
      ) : (
        <div className="inst-body">
          <div className="inst-table-wrap">
            <table className="inst-table">
              <thead>
                <tr>
                  <th>單位名稱</th>
                  <th>買進（億元）</th>
                  <th>賣出（億元）</th>
                  <th>買賣差額（億元）</th>
                </tr>
              </thead>
              <tbody>
                <AmountRow label="自營商（自行買賣）" amount={flow.dealer_proprietary} sub />
                <AmountRow label="自營商（避險）" amount={flow.dealer_hedge} sub />
                <AmountRow label="投信" amount={flow.trust} />
                <AmountRow label="外資及陸資" amount={flow.foreign} />
                <AmountRow label="外資自營商" amount={flow.foreign_dealer} sub />
              </tbody>
              <tfoot>
                <AmountRow label="合計" amount={flow.total} />
              </tfoot>
            </table>
          </div>

          <aside className="inst-summary" aria-label="三大法人摘要">
            <div>
              <div className="inst-total-label">三大法人合計淨額</div>
              <div className={`inst-total mono ${netClass(flow.total.net)}`}>
                {fmtNet(flow.total.net)}<small>億元</small>
              </div>
            </div>

            <div className="inst-groups">
              {(() => {
                const maximum = Math.max(1, ...GROUPS.map(({ key }) => Math.abs(flow[key].net)));
                return GROUPS.map(({ key, label, color }) => (
                  <div className="inst-group" key={key}>
                    <strong>{label}</strong>
                    <span><i style={{ width: `${Math.abs(flow[key].net) / maximum * 100}%`, background: color }} /></span>
                    <output className={`mono ${netClass(flow[key].net)}`}>{fmtNet(flow[key].net)}</output>
                  </div>
                ));
              })()}
            </div>

            <div className="inst-ratio">
              <div><span>法人成交比重</span><strong className="mono">
                {flow.turnover_ratio === null ? '—' : `${flow.turnover_ratio.toFixed(2)}%`}
              </strong></div>
              <span className="inst-ratio-track"><i style={{ width: `${Math.min(100, flow.turnover_ratio ?? 0)}%` }} /></span>
            </div>
          </aside>
        </div>
      )}

      <footer className="inst-foot">
        外資自營商已包含於自營商金額，依證交所規則不重複計入合計。
      </footer>
    </section>
  );
}
