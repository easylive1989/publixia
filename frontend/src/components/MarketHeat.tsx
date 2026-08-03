import { useState } from 'react';
import type { MarketHeatDay, MarketHeatPayload } from '@/hooks/useMarketHeat';
import { HEAT_LEVELS, HEAT_META, fmtBillion, fmtPercentile } from '@/lib/market-heat';

// ---- chart geometry (viewBox units; rendered responsive at width 100%) ----
const W = 660;
const H = 190;
const PAD_L = 46;   // room for the 億元 tick labels
const PAD_R = 6;
const PAD_T = 10;
const PAD_B = 20;   // room for month labels

export function MarketHeat({ data, isLoading }: { data?: MarketHeatPayload; isLoading: boolean }) {
  if (isLoading) return <div className="empty-note">載入中…</div>;
  const latest = data?.latest;
  if (!latest) {
    return <div className="empty-note">大盤資料同步中，第一次同步需要幾分鐘，稍後再來看看。</div>;
  }
  const meta = HEAT_META[latest.level];
  return (
    <section className="heat">
      <div className="heat-today">
        <div
          className="heat-stamp"
          style={{ background: meta.color, color: meta.darkText ? 'var(--ink)' : '#fff' }}
        >
          <span className="zh">{latest.label}</span>
          <span className="en">{meta.en}</span>
        </div>
        <div className="heat-date mono">{latest.date}</div>
        <dl className="heat-stats">
          <div><dt>加權指數</dt><dd className="mono">{latest.taiex_close.toLocaleString('en-US')}</dd></div>
          <div><dt>成交金額</dt><dd className="mono">{fmtBillion(latest.turnover)} 億</dd></div>
          <div><dt>位階常態</dt><dd className="mono">{fmtBillion(latest.expected_turnover)} 億</dd></div>
          <div><dt>量能比</dt><dd className="mono">×{latest.volume_ratio.toFixed(2)}</dd></div>
          <div><dt>近一年百分位</dt><dd className="mono">{fmtPercentile(latest.percentile)}</dd></div>
        </dl>
        <HeatMeter percentile={latest.percentile} />
      </div>
      <div className="heat-chart">
        <HeatChart days={data.days} />
        <div className="heat-legend">
          {HEAT_LEVELS.map((lv) => (
            <span key={lv} className="heat-key">
              <i style={{ background: HEAT_META[lv].color }} />{HEAT_META[lv].zh}
            </span>
          ))}
          <span className="heat-key line-key"><i className="expected" />位階常態</span>
        </div>
      </div>
    </section>
  );
}

/** 0–100 殘差百分位 meter：五段判讀色帶 + 今日位置標記。 */
function HeatMeter({ percentile }: { percentile: number }) {
  return (
    <div className="heat-meter" role="img" aria-label={`近一年殘差百分位 ${Math.round(percentile * 100)}`}>
      <div className="heat-meter-track">
        {HEAT_LEVELS.map((lv) => (
          <i key={lv} style={{ background: HEAT_META[lv].color }} />
        ))}
        <span className="heat-meter-pin" style={{ left: `${percentile * 100}%` }} />
      </div>
      <div className="heat-meter-cap"><span>冷</span><span>熱</span></div>
    </div>
  );
}

/** 近 N 個交易日：成交金額 bar（依判讀上色）＋ 位階常態折線。 */
function HeatChart({ days }: { days: MarketHeatDay[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (days.length === 0) return null;

  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const maxY = Math.max(...days.map((d) => Math.max(d.turnover, d.expected_turnover))) * 1.06;
  const slot = innerW / days.length;
  const barW = Math.max(2, Math.min(9, slot - 2)); // ≥2px gap between fills
  const x = (i: number) => PAD_L + slot * i + slot / 2;
  const y = (v: number) => PAD_T + innerH * (1 - v / maxY);

  const expectedPath = days
    .map((d, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(d.expected_turnover).toFixed(1)}`)
    .join(' ');

  const ticks = [0.25, 0.5, 0.75, 1].map((f) => Math.round((maxY * f) / 1000) * 1000)
    .filter((v, i, a) => v > 0 && a.indexOf(v) === i);
  const monthStarts = days
    .map((d, i) => ({ d, i }))
    .filter(({ d, i }) => i > 0 && d.date.slice(5, 7) !== days[i - 1].date.slice(5, 7));

  const hovered = hover === null ? null : days[hover];
  return (
    <div className="heat-plot">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD_L} x2={W - PAD_R} y1={y(v)} y2={y(v)} className="grid" />
            <text x={PAD_L - 6} y={y(v) + 3.5} className="tick" textAnchor="end">{fmtBillion(v)}</text>
          </g>
        ))}
        {monthStarts.map(({ d, i }) => (
          <text key={d.date} x={x(i)} y={H - 6} className="tick" textAnchor="middle">
            {Number(d.date.slice(5, 7))}月
          </text>
        ))}
        {days.map((d, i) => (
          <rect
            key={d.date}
            x={x(i) - barW / 2}
            y={y(d.turnover)}
            width={barW}
            height={Math.max(1, PAD_T + innerH - y(d.turnover))}
            rx={1.5}
            fill={HEAT_META[d.level].color}
            opacity={hover === null || hover === i ? 1 : 0.45}
          />
        ))}
        <path d={expectedPath} className="expected-line" />
        {/* hover hit targets: full-height slots, wider than the bars */}
        {days.map((d, i) => (
          <rect
            key={`h-${d.date}`}
            x={PAD_L + slot * i}
            y={PAD_T}
            width={slot}
            height={innerH}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>
      {hovered && hover !== null && (
        <div
          className="heat-tip"
          style={{
            left: `${((x(hover)) / W) * 100}%`,
            transform: `translateX(${hover > days.length / 2 ? '-100%' : '0'})`,
          }}
        >
          <div className="tip-head">
            <span className="mono">{hovered.date}</span>
            <span className="tip-label" style={{ color: HEAT_META[hovered.level].color }}>
              {hovered.label}
            </span>
          </div>
          <div className="tip-row"><span>成交金額</span><span className="mono">{fmtBillion(hovered.turnover)} 億</span></div>
          <div className="tip-row"><span>位階常態</span><span className="mono">{fmtBillion(hovered.expected_turnover)} 億</span></div>
          <div className="tip-row"><span>量能比</span><span className="mono">×{hovered.volume_ratio.toFixed(2)}</span></div>
          <div className="tip-row"><span>近一年百分位</span><span className="mono">{fmtPercentile(hovered.percentile)}</span></div>
        </div>
      )}
    </div>
  );
}
