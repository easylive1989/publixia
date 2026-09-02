import { useEffect, useMemo, useRef, useState } from 'react';
import type { InstitutionalFlow, MarketHeatDay } from '@/hooks/useMarketHeat';
import { HEAT_LEVELS, HEAT_META, fmtBillion, fmtPercentile, niceTicks } from '@/lib/market-heat';
import type { MarketConfig } from '@/lib/markets';

const H = 300;
const PAD_L = 56;
const PAD_R = 58;
const PAD_T = 14;
const PAD_B = 25;
const INDEX_BOTTOM = 120;
const BAR_TOP = 128;
const BAR_BOTTOM = H - PAD_B;
const SLOT_MIN = 12;

export const INSTITUTION_COLORS = {
  foreign: '#c4513f',
  trust: '#5269b4',
  dealer: '#ce963b',
};

type InstitutionKey = keyof typeof INSTITUTION_COLORS;

function institutionNets(flow?: InstitutionalFlow | null): Record<InstitutionKey, number> {
  return {
    foreign: flow?.foreign.net ?? 0,
    trust: flow?.trust.net ?? 0,
    dealer: flow?.dealer.net ?? 0,
  };
}

function axisCeiling(value: number): number {
  if (!(value > 0)) return 100;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const nice = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10]
    .find((candidate) => candidate >= normalized) ?? 10;
  return nice * magnitude;
}

function fmtNet(value: number): string {
  if (Math.abs(value) < 0.005) return '0.00';
  return `${value > 0 ? '+' : ''}${value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

interface BarSegment {
  key: InstitutionKey;
  y: number;
  height: number;
}

export function IndexChart({
  days,
  market,
  selectedDate,
  onSelectDate,
}: {
  days: MarketHeatDay[];
  market: MarketConfig;
  selectedDate: string;
  onSelectDate: (date: string) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const W = Math.max(660, Math.round(PAD_L + PAD_R + days.length * SLOT_MIN));
  const innerW = W - PAD_L - PAD_R;
  const slot = days.length ? innerW / days.length : 0;
  const barW = Math.max(7, Math.min(14, slot * 0.78));
  const x = (index: number) => PAD_L + slot * index + slot / 2;
  const selectedIndex = Math.max(0, days.findIndex((day) => day.date === selectedDate));

  const closes = days.map((day) => day.index_close);
  const closeMin = days.length ? Math.min(...closes) : 0;
  const closeMax = days.length ? Math.max(...closes) : 1;
  const closePad = (closeMax - closeMin) * 0.08 || Math.max(1, closeMax * 0.01);
  const indexMin = closeMin - closePad;
  const indexMax = closeMax + closePad;
  const indexY = (value: number) => (
    PAD_T + (INDEX_BOTTOM - PAD_T) * (1 - (value - indexMin) / (indexMax - indexMin))
  );

  const institutionalExtents = days.map((day) => {
    const values = Object.values(institutionNets(day.institutional));
    const positive = values.filter((value) => value > 0).reduce((sum, value) => sum + value, 0);
    const negative = Math.abs(values.filter((value) => value < 0).reduce((sum, value) => sum + value, 0));
    return { positive, negative };
  });
  const positiveAxis = axisCeiling(Math.max(0, ...institutionalExtents.map(({ positive }) => positive)));
  const negativeAxis = axisCeiling(Math.max(0, ...institutionalExtents.map(({ negative }) => negative)));
  // 上下軸共用相同的「每億元像素數」，零軸依兩側資料範圍移動，
  // 避免較小的一側浪費半個法人圖區，同時維持柱高可直接互相比較。
  const barZero = BAR_TOP + (BAR_BOTTOM - BAR_TOP) * positiveAxis / (positiveAxis + negativeAxis);
  const positiveScale = (barZero - BAR_TOP) / positiveAxis;
  const negativeScale = (BAR_BOTTOM - barZero) / negativeAxis;

  const segments = (day: MarketHeatDay): BarSegment[] => {
    const values = institutionNets(day.institutional);
    let positiveY = barZero;
    let negativeY = barZero;
    return (Object.keys(INSTITUTION_COLORS) as InstitutionKey[]).map((key) => {
      const value = values[key];
      const scale = value >= 0 ? positiveScale : negativeScale;
      const height = Math.max(value === 0 ? 0 : 1, Math.abs(value) * scale);
      if (value >= 0) {
        positiveY -= height;
        return { key, y: positiveY, height };
      }
      const result = { key, y: negativeY, height };
      negativeY += height;
      return result;
    });
  };

  const linePath = days
    .map((day, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${indexY(day.index_close).toFixed(1)}`)
    .join(' ');
  const monthStarts = days
    .map((day, index) => ({ day, index }))
    .filter(({ day, index }) => index === 0 || day.date.slice(5, 7) !== days[index - 1].date.slice(5, 7));
  const hovered = hover === null ? null : days[hover];

  useEffect(() => {
    if (days.length === 0) return;
    const element = scrollRef.current;
    if (!element) return;
    element.scrollLeft = Math.max(0, x(selectedIndex) - element.clientWidth / 2);
  }, [days, selectedIndex, W]);

  if (days.length === 0) return null;

  return (
    <div className="idx-plot-scroll" ref={scrollRef}>
      <div className="heat-plot idx-combo-plot" style={{ width: `${W}px` }}>
        <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}>
          <rect
            className="idx-selected-band"
            x={PAD_L + slot * selectedIndex}
            y={PAD_T}
            width={slot}
            height={BAR_BOTTOM - PAD_T}
          />

          {niceTicks(indexMin, indexMax, 3).map((value) => (
            <g key={value}>
              <line x1={PAD_L} x2={W - PAD_R} y1={indexY(value)} y2={indexY(value)} className="grid" />
              <text x={W - PAD_R + 6} y={indexY(value) + 3.5} className="tick">
                {value.toLocaleString('en-US')}
              </text>
            </g>
          ))}

          <line x1={PAD_L} x2={W - PAD_R} y1={BAR_TOP} y2={BAR_TOP} className="grid" />
          <line x1={PAD_L} x2={W - PAD_R} y1={barZero} y2={barZero} className="idx-zero" />
          <line x1={PAD_L} x2={W - PAD_R} y1={BAR_BOTTOM} y2={BAR_BOTTOM} className="grid" />
          <text x={PAD_L - 6} y={BAR_TOP + 3.5} className="tick" textAnchor="end">+{fmtBillion(positiveAxis)}</text>
          <text x={PAD_L - 6} y={barZero + 3.5} className="tick" textAnchor="end">0</text>
          <text x={PAD_L - 6} y={BAR_BOTTOM + 3.5} className="tick" textAnchor="end">−{fmtBillion(negativeAxis)}</text>

          {monthStarts.map(({ day, index }) => (
            <g key={day.date}>
              {index > 0 && <line x1={x(index)} x2={x(index)} y1={PAD_T} y2={BAR_BOTTOM} className="idx-month-line" />}
              <text x={x(index)} y={H - 7} className="tick" textAnchor="middle">
                {day.date.slice(5, 7) === '01' ? `${day.date.slice(0, 4)}/1` : `${Number(day.date.slice(5, 7))}月`}
              </text>
            </g>
          ))}

          {days.map((day, index) => (
            <g key={`bar-${day.date}`} className="idx-inst-bar">
              {segments(day).map((segment) => segment.height > 0 && (
                <rect
                  key={segment.key}
                  x={x(index) - barW / 2}
                  y={segment.y}
                  width={barW}
                  height={segment.height}
                  rx={1}
                  fill={INSTITUTION_COLORS[segment.key]}
                  className="idx-inst-segment"
                />
              ))}
            </g>
          ))}

          <path d={linePath} className="idx-line" />
          {days.map((day, index) => (
            <circle
              key={`dot-${day.date}`}
              cx={x(index)}
              cy={indexY(day.index_close)}
              r={index === selectedIndex ? 5.5 : Math.max(2.75, Math.min(3.75, slot * 0.22))}
              fill={HEAT_META[day.level].color}
              className={`idx-dot${index === selectedIndex ? ' selected' : ''}`}
            />
          ))}

          {days.map((day, index) => (
            <rect
              key={`hit-${day.date}`}
              x={PAD_L + slot * index}
              y={PAD_T}
              width={slot}
              height={BAR_BOTTOM - PAD_T}
              fill="transparent"
              className="idx-hit"
              role="button"
              aria-label={`選擇 ${day.date}`}
              tabIndex={0}
              onMouseEnter={() => setHover(index)}
              onClick={() => onSelectDate(day.date)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelectDate(day.date);
                }
              }}
            />
          ))}
        </svg>

        {hovered && hover !== null && (
          <div
            className="heat-tip idx-combo-tip"
            style={{
              left: `${(x(hover) / W) * 100}%`,
              transform: `translateX(${hover > days.length / 2 ? '-100%' : '0'})`,
            }}
          >
            <div className="tip-head">
              <span className="mono">{hovered.date}</span>
              <span className="tip-label">點選切換</span>
            </div>
            <div className="tip-row"><span>{market.indexLabel}</span><span className="mono">{hovered.index_close.toLocaleString('en-US')}</span></div>
            <div className="tip-row"><span>{market.volumeLabel}</span><span className="mono">{fmtBillion(hovered.turnover)} {market.unit}</span></div>
            <div className="tip-row"><span>量能</span><span className="mono">{hovered.label} · {fmtPercentile(hovered.percentile)}</span></div>
            {hovered.institutional ? (
              <>
                <div className="tip-row"><span>外資</span><span className="mono">{fmtNet(hovered.institutional.foreign.net)} 億</span></div>
                <div className="tip-row"><span>投信</span><span className="mono">{fmtNet(hovered.institutional.trust.net)} 億</span></div>
                <div className="tip-row"><span>自營商</span><span className="mono">{fmtNet(hovered.institutional.dealer.net)} 億</span></div>
              </>
            ) : (
              <div className="tip-row"><span>法人</span><span>尚未同步</span></div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function IndexLegend({ market }: { market: MarketConfig }) {
  const items = useMemo(() => [
    { label: '外資', color: INSTITUTION_COLORS.foreign },
    { label: '投信', color: INSTITUTION_COLORS.trust },
    { label: '自營商', color: INSTITUTION_COLORS.dealer },
  ], []);
  return (
    <div className="heat-legend idx-combo-legend">
      <span className="heat-key line-key"><i className="idx" />{market.indexLabel}</span>
      {HEAT_LEVELS.map((level) => (
        <span className="heat-key dot-key" key={level}>
          <i style={{ background: HEAT_META[level].color }} />{HEAT_META[level].zh}
        </span>
      ))}
      {items.map((item) => (
        <span className="heat-key" key={item.label}>
          <i style={{ background: item.color }} />{item.label}
        </span>
      ))}
      <span className="idx-zero-note">零軸上方為買超，下方為賣超</span>
    </div>
  );
}
