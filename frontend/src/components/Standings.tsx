import { initialOf, personHue } from '@/lib/person-hue';
import { fmtPct } from '@/lib/verdict';
import type { Standing } from '@/hooks/usePeople';

function StandingRow({
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
  return (
    <div
      className={'st-row' + (s.rank === 1 ? ' rank-1' : '') + (active ? ' is-active' : '') + (s.dnp ? ' dnp' : '')}
      style={{ '--hue': personHue(s.person_key, allKeys) } as React.CSSProperties}
      onClick={onClick}
    >
      <div>{s.dnp ? <span className="rank-tag">DNP</span> : <span className="rank">{s.rank}</span>}</div>
      <div className="player">
        <span className="jersey">{initialOf(s.display_name)}</span>
        <div className="player-meta">
          <div className="player-name">{s.display_name}</div>
        </div>
      </div>
      <div className="st-cell-win">
        {s.dnp ? (
          <span className="record"><span className="sub">未上場</span></span>
        ) : (
          <span className="record">
            <span className="w">{s.win_count}</span>
            <span className="sep">–</span>
            <span className="l">{s.loss_count}</span>
            <span className="sub">命中 / 槓龜</span>
          </span>
        )}
      </div>
      <div className="st-cell-pct">
        {s.win_rate == null ? (
          <span className="winpct" style={{ color: 'var(--ink-3)' }}>—</span>
        ) : (
          <span className="winpct">{Math.round(s.win_rate * 100)}%</span>
        )}
      </div>
      <div className="score">
        {s.cum_return == null ? (
          <>
            <span className="big" style={{ color: 'var(--ink-3)', fontSize: 22 }}>—</span>
            <span className="cap">未上場</span>
          </>
        ) : (
          <>
            <span className={'big ' + (s.cum_return >= 0 ? 'up' : 'down')}>{fmtPct(s.cum_return)}</span>
            <span className="cap">累積跟單損益</span>
          </>
        )}
      </div>
      <div className="st-cell-form">
        <div className="form">
          {s.form.length === 0 ? (
            <span className="form-empty">尚無喊單</span>
          ) : (
            s.form.slice(0, 5).map((r, i) => (
              <span key={i} className={'form-dot ' + r}>{r === 'w' ? 'W' : 'L'}</span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export function Standings({
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
    <div className="standings">
      <div className="st-row st-head">
        <div>名次</div>
        <div>老師</div>
        <div className="col-win">戰績</div>
        <div className="col-pct">命中率</div>
        <div>累積損益</div>
        <div className="col-form">近 5 場</div>
      </div>
      <div className="st-body">
        {standings.map((s) => (
          <StandingRow
            key={s.person_key}
            s={s}
            allKeys={allKeys}
            active={person === s.person_key}
            onClick={() => onPerson(person === s.person_key ? 'all' : s.person_key)}
          />
        ))}
      </div>
    </div>
  );
}
