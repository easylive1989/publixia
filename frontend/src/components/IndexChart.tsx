import { useEffect, useRef, useState } from 'react';
import type { MarketHeatDay } from '@/hooks/useMarketHeat';
import { HEAT_LEVELS, HEAT_META, fmtBillion, fmtPercentile, niceTicks } from '@/lib/market-heat';
import type { MarketConfig } from '@/lib/markets';

// 大盤位階 vs 量能判讀：指數走勢（灰線，僅承載位階）＋ 每日判讀（點色）。
const H = 220;
const PAD_L = 52;   // room for 5-digit index ticks
const PAD_R = 8;
const PAD_T = 12;
const PAD_B = 22;
const SLOT_MIN = 5.5; // px per trading day before the chart starts scrolling

export function IndexChart({ days, market }: { days: MarketHeatDay[]; market: MarketConfig }) {
  const [hover, setHover] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth; // land on the latest days
  }, [days]);
  if (days.length === 0) return null;

  const W = Math.max(660, Math.round(PAD_L + PAD_R + days.length * SLOT_MIN));
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const closes = days.map((d) => d.index_close);
  const lo = Math.min(...closes);
  const hi = Math.max(...closes);
  // index never starts at 0 — pad the observed range so the trend fills the box
  const pad = (hi - lo) * 0.08 || Math.max(1, hi * 0.01);
  const yMin = lo - pad;
  const yMax = hi + pad;

  const slot = innerW / days.length;
  const r = Math.max(2, Math.min(4, slot * 0.36));
  const x = (i: number) => PAD_L + slot * i + slot / 2;
  const y = (v: number) => PAD_T + innerH * (1 - (v - yMin) / (yMax - yMin));

  const linePath = days
    .map((d, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(d.index_close).toFixed(1)}`)
    .join(' ');
  const monthStarts = days
    .map((d, i) => ({ d, i }))
    .filter(({ d, i }) => i > 0 && d.date.slice(5, 7) !== days[i - 1].date.slice(5, 7));

  const hovered = hover === null ? null : days[hover];
  return (
    <div className="idx-plot-scroll" ref={scrollRef}>
      <div className="heat-plot" style={{ width: `${W}px` }}>
        <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}>
          {niceTicks(yMin, yMax).map((v) => (
            <g key={v}>
              <line x1={PAD_L} x2={W - PAD_R} y1={y(v)} y2={y(v)} className="grid" />
              <text x={PAD_L - 6} y={y(v) + 3.5} className="tick" textAnchor="end">
                {v.toLocaleString('en-US')}
              </text>
            </g>
          ))}
          {monthStarts.map(({ d, i }) => (
            <text key={d.date} x={x(i)} y={H - 6} className="tick" textAnchor="middle">
              {d.date.slice(5, 7) === '01' ? `${d.date.slice(0, 4)}/1` : `${Number(d.date.slice(5, 7))}月`}
            </text>
          ))}
          {/* the line only carries 位階; 冷熱 rides on the dots */}
          <path d={linePath} className="idx-line" />
          {days.map((d, i) => (
            <circle
              key={d.date}
              cx={x(i)}
              cy={y(d.index_close)}
              r={hover === i ? r + 1.5 : r}
              fill={HEAT_META[d.level].color}
              className="idx-dot"
              opacity={hover === null || hover === i ? 1 : 0.5}
            />
          ))}
          {/* hover hit targets: full-height slots, wider than the dots */}
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
              left: `${(x(hover) / W) * 100}%`,
              transform: `translateX(${hover > days.length / 2 ? '-100%' : '0'})`,
            }}
          >
            <div className="tip-head">
              <span className="mono">{hovered.date}</span>
              <span className="tip-label" style={{ color: HEAT_META[hovered.level].color }}>
                {hovered.label}
              </span>
            </div>
            <div className="tip-row"><span>{market.indexLabel}</span><span className="mono">{hovered.index_close.toLocaleString('en-US')}</span></div>
            <div className="tip-row"><span>{market.volumeLabel}</span><span className="mono">{fmtBillion(hovered.turnover)} {market.unit}</span></div>
            <div className="tip-row"><span>量能比</span><span className="mono">×{hovered.volume_ratio.toFixed(2)}</span></div>
            <div className="tip-row"><span>近一年百分位</span><span className="mono">{fmtPercentile(hovered.percentile)}</span></div>
          </div>
        )}
      </div>
    </div>
  );
}

/** 點色圖例（圓點對應圖上的 mark 形狀）＋ 指數線。 */
export function IndexLegend({ market }: { market: MarketConfig }) {
  return (
    <div className="heat-legend">
      <span className="heat-key line-key"><i className="idx" />{market.indexLabel}</span>
      {HEAT_LEVELS.map((lv) => (
        <span key={lv} className="heat-key dot-key">
          <i style={{ background: HEAT_META[lv].color }} />{HEAT_META[lv].zh}
        </span>
      ))}
    </div>
  );
}
