import { useEffect, useRef, useState } from 'react';
import type { MarketHeatDay } from '@/hooks/useMarketHeat';
import { niceTicks } from '@/lib/market-heat';
import type { MarketConfig } from '@/lib/markets';

const H = 270;
const PAD_L = 48;
const PAD_R = 70;
const PAD_T = 18;
const PAD_B = 30;
const SLOT_MIN = 11;
const SCORE_TICKS = [0, 20, 40, 60, 80, 100];

const SENTIMENT_COLORS: Record<string, string> = {
  極度恐懼: '#2368b4',
  恐懼: '#79add4',
  中性: '#b9b5ad',
  貪婪: '#dc954d',
  極度貪婪: '#bd362a',
};

const BANDS = [
  { min: 0, max: 20, color: SENTIMENT_COLORS.極度恐懼 },
  { min: 20, max: 40, color: SENTIMENT_COLORS.恐懼 },
  { min: 40, max: 60, color: SENTIMENT_COLORS.中性 },
  { min: 60, max: 80, color: SENTIMENT_COLORS.貪婪 },
  { min: 80, max: 100, color: SENTIMENT_COLORS.極度貪婪 },
];

/** 缺少漲跌家數時切斷折線，不用跨日連線製造不存在的數值。 */
function sentimentPaths(
  rows: MarketHeatDay[],
  x: (index: number) => number,
  y: (score: number) => number,
): string[] {
  const paths: string[] = [];
  let points: string[] = [];
  const flush = () => {
    if (points.length) paths.push(points.join(' '));
    points = [];
  };
  rows.forEach((row, index) => {
    if (!row.sentiment) {
      flush();
      return;
    }
    points.push(`${points.length ? 'L' : 'M'}${x(index).toFixed(1)},${y(row.sentiment.score).toFixed(1)}`);
  });
  flush();
  return paths;
}

/** 左軸固定為情緒 0～100，右軸為同期間大盤指數。 */
export function SentimentChart({
  rows,
  market,
}: {
  rows: MarketHeatDay[];
  market: MarketConfig;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const W = Math.max(660, Math.round(PAD_L + PAD_R + rows.length * SLOT_MIN));
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const slot = rows.length ? innerW / rows.length : 0;
  const x = (index: number) => PAD_L + slot * index + slot / 2;
  const scoreY = (score: number) => PAD_T + innerH * (1 - score / 100);

  const closes = rows.map((row) => row.index_close);
  const closeMin = rows.length ? Math.min(...closes) : 0;
  const closeMax = rows.length ? Math.max(...closes) : 1;
  const closePad = (closeMax - closeMin) * 0.08 || Math.max(1, closeMax * 0.01);
  const indexMin = closeMin - closePad;
  const indexMax = closeMax + closePad;
  const indexY = (value: number) => (
    PAD_T + innerH * (1 - (value - indexMin) / (indexMax - indexMin))
  );

  const indexPath = rows
    .map((row, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${indexY(row.index_close).toFixed(1)}`)
    .join(' ');
  const scorePaths = sentimentPaths(rows, x, scoreY);
  const monthStarts = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row, index }) => index === 0 || row.date.slice(5, 7) !== rows[index - 1].date.slice(5, 7));
  const hovered = hover === null ? null : rows[hover];
  const hasSentiment = rows.some((row) => row.sentiment);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollLeft = element.scrollWidth;
  }, [rows]);

  if (rows.length === 0) return null;

  return (
    <section className="panel sentiment-panel" aria-labelledby="sentiment-title">
      <div className="idx-panel-head">
        <h2 id="sentiment-title" className="panel-title">自算恐懼貪婪指數 vs {market.indexLabel}</h2>
        <span>左軸 0–100｜右軸 {market.indexLabel}</span>
      </div>
      <div className="sentiment-chart-scroll" ref={scrollRef}>
        <div className="heat-plot sentiment-plot" style={{ width: `${W}px` }}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label={`自算恐懼貪婪指數與${market.indexLabel}走勢圖`}
            onMouseLeave={() => setHover(null)}
          >
            {BANDS.map((band) => (
              <rect
                key={band.min}
                x={PAD_L}
                y={scoreY(band.max)}
                width={innerW}
                height={scoreY(band.min) - scoreY(band.max)}
                fill={band.color}
                className="sentiment-band"
              />
            ))}

            {SCORE_TICKS.map((score) => (
              <g key={score}>
                <line x1={PAD_L} x2={W - PAD_R} y1={scoreY(score)} y2={scoreY(score)} className="grid" />
                <text x={PAD_L - 7} y={scoreY(score) + 3.5} className="tick" textAnchor="end">{score}</text>
              </g>
            ))}

            {niceTicks(indexMin, indexMax, 4).map((value) => (
              <text key={value} x={W - PAD_R + 7} y={indexY(value) + 3.5} className="tick">
                {Math.round(value).toLocaleString('en-US')}
              </text>
            ))}

            {monthStarts.map(({ row, index }) => (
              <g key={row.date}>
                {index > 0 && (
                  <line x1={x(index)} x2={x(index)} y1={PAD_T} y2={H - PAD_B} className="sentiment-month-line" />
                )}
                <text x={x(index)} y={H - 8} className="tick" textAnchor="middle">
                  {row.date.slice(5, 7) === '01' ? `${row.date.slice(0, 4)}/1` : `${Number(row.date.slice(5, 7))}月`}
                </text>
              </g>
            ))}

            <path d={indexPath} className="sentiment-index-line" />
            {scorePaths.map((path, index) => (
              <path key={index} d={path} className="sentiment-score-line" />
            ))}
            {rows.map((row, index) => row.sentiment && (
              <circle
                key={row.date}
                cx={x(index)}
                cy={scoreY(row.sentiment.score)}
                r={3.2}
                fill={SENTIMENT_COLORS[row.sentiment.label] ?? SENTIMENT_COLORS.中性}
                className="sentiment-dot"
              />
            ))}

            {rows.map((row, index) => (
              <rect
                key={`hit-${row.date}`}
                x={PAD_L + slot * index}
                y={PAD_T}
                width={slot}
                height={innerH}
                fill="transparent"
                className="sentiment-hit"
                role="img"
                tabIndex={0}
                aria-label={`${row.date}，情緒指數${row.sentiment ? row.sentiment.score.toFixed(2) : '尚無資料'}，${market.indexLabel}${row.index_close.toFixed(2)}`}
                onMouseEnter={() => setHover(index)}
                onFocus={() => setHover(index)}
                onBlur={() => setHover(null)}
              />
            ))}
          </svg>

          {hovered && hover !== null && (
            <div
              className="heat-tip sentiment-tip"
              style={{
                left: `${(x(hover) / W) * 100}%`,
                transform: `translateX(${hover > rows.length / 2 ? '-100%' : '0'})`,
              }}
            >
              <div className="tip-head"><span className="mono">{hovered.date}</span></div>
              <div className="tip-row">
                <span>情緒指數</span>
                <span className="mono">
                  {hovered.sentiment ? `${hovered.sentiment.score.toFixed(2)} · ${hovered.sentiment.label}` : '等待漲跌家數'}
                </span>
              </div>
              <div className="tip-row">
                <span>{market.indexLabel}</span>
                <span className="mono">{hovered.index_close.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="heat-legend sentiment-legend">
        <span className="heat-key line-key"><i className="sentiment-score-key" />自算恐懼貪婪指數</span>
        <span className="heat-key line-key"><i className="sentiment-index-key" />{market.indexLabel}</span>
        {Object.entries(SENTIMENT_COLORS).map(([label, color]) => (
          <span className="heat-key" key={label}><i style={{ background: color }} />{label}</span>
        ))}
      </div>
      {!hasSentiment && <p className="sentiment-empty">漲跌家數同步完成後，情緒折線會顯示在這裡。</p>}
    </section>
  );
}
