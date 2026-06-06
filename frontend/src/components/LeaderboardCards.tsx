import { initialOf, personHue } from '@/lib/person-hue';
import { fmtPct } from '@/lib/verdict';
import type { Standing } from '@/hooks/usePeople';

function Card({
  s,
  allKeys,
  active,
  onClick,
}: {
  s: Standing;
  allKeys: string[];
  active: boolean;
  onClick: () => void;
}) {
  const cum = s.cum_return ?? 0;
  const trackW = s.win_rate == null ? 0 : Math.round(s.win_rate * 100);
  return (
    <button
      className={'lb' + (s.rank === 1 ? ' rank-1' : '') + (active ? ' active' : '') + (s.dnp ? ' dnp' : '')}
      style={{ '--hue': personHue(s.person_key, allKeys) } as React.CSSProperties}
      onClick={onClick}
    >
      <div className="lb-top">
        <span className="jersey" style={{ width: 30, height: 30, fontSize: 14 }}>
          {initialOf(s.display_name)}
        </span>
        <span className="lb-name">{s.display_name}</span>
        <span className="lb-rank">{s.dnp ? '–' : s.rank}</span>
      </div>
      {s.dnp ? (
        <div className="lb-empty">尚無喊單戰績</div>
      ) : (
        <>
          <div className="lb-stats">
            <div className="lb-stat">
              <span className="k">命中率</span>
              <span className="v">{Math.round((s.win_rate ?? 0) * 100)}%</span>
            </div>
            <div className="lb-stat">
              <span className="k">累積損益</span>
              <span className={'v ' + (cum >= 0 ? 'up' : 'down')}>{fmtPct(cum)}</span>
            </div>
          </div>
          <div className="lb-track">
            <i style={{ width: `${trackW}%`, background: cum >= 0 ? 'var(--win)' : 'var(--loss)' }} />
          </div>
        </>
      )}
    </button>
  );
}

export function LeaderboardCards({
  standings,
  allKeys,
  person,
  onPerson,
}: {
  standings: Standing[];
  allKeys: string[];
  person: string;
  onPerson: (p: string) => void;
}) {
  return (
    <div className="board">
      {standings.map((s) => (
        <Card
          key={s.person_key}
          s={s}
          allKeys={allKeys}
          active={person === s.person_key}
          onClick={() => onPerson(person === s.person_key ? 'all' : s.person_key)}
        />
      ))}
    </div>
  );
}
