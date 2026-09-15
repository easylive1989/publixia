import type { MarketHeatDay } from '@/hooks/useMarketHeat';
import type { MarketConfig } from '@/lib/markets';

const SENTIMENT_TONE: Record<string, string> = {
  極度恐懼: 'extreme-fear',
  恐懼: 'fear',
  中性: 'neutral',
  貪婪: 'greed',
  極度貪婪: 'extreme-greed',
};

function fmtIndex(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
/** 自算情緒指數和大盤收盤並排，避免跨圖目測兩條不同尺度的線。 */
export function SentimentTable({
  rows,
  market,
}: {
  rows: MarketHeatDay[];
  market: MarketConfig;
}) {
  if (rows.length === 0) return null;
  const desc = [...rows].reverse();

  return (
    <section className="panel sentiment-panel" aria-labelledby="sentiment-title">
      <div className="idx-panel-head">
        <h2 id="sentiment-title" className="panel-title">自算情緒指數 vs {market.indexLabel}</h2>
        <span>0 為極度恐懼、100 為極度貪婪｜v1 公開公式</span>
      </div>
      <div className="sentiment-table-wrap">
        <table className="sheet sentiment-sheet">
          <thead>
            <tr>
              <th>日期</th>
              <th>自算情緒指數</th>
              <th>市場情緒</th>
              <th>{market.indexLabel}</th>
            </tr>
          </thead>
          <tbody>
            {desc.map((day) => (
              <tr key={day.date}>
                <td className="mono">{day.date}</td>
                <td className="mono sentiment-score">
                  {day.sentiment ? day.sentiment.score.toFixed(2) : '—'}
                </td>
                <td>
                  {day.sentiment ? (
                    <span className={`sentiment-badge ${SENTIMENT_TONE[day.sentiment.label] ?? 'neutral'}`}>
                      {day.sentiment.label}
                    </span>
                  ) : (
                    <span className="sentiment-missing">等待漲跌家數</span>
                  )}
                </td>
                <td className="mono">{fmtIndex(day.index_close)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
