/* global React, ReactDOM, useTweaks, TweaksPanel, TweakSection, TweakRadio, TweakToggle */
const { useState, useMemo } = React;
const { people, posts } = window.TRACKER_DATA;

/* ---------- helpers ---------- */
const isLong = (s) => s.type === 'long' || s.type === 'buy';
const fmtPct = (v) => (v > 0 ? '+' : '') + v.toFixed(1) + '%';
function pnl(sig, h) { const r = sig.perf[h]; if (r == null) return null; return isLong(sig) ? r : -r; }

function sparkPoints(sig) {
  let seed = [...(sig.ticker + sig.type)].reduce((a, c) => a + c.charCodeAt(0), 0);
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  const n = 24, end = pnl(sig, 'latest') ?? (isLong(sig) ? 2 : -2), arr = [];
  let v = 0;
  for (let i = 0; i < n; i++) { v += (rnd() - 0.5) * 3.2; arr.push(v); }
  for (let i = 0; i < n; i++) arr[i] += (end / 8) * (i / (n - 1)) ** 2;
  const mn = Math.min(...arr), mx = Math.max(...arr), sp = (mx - mn) || 1;
  return arr.map((p, i) => [i / (n - 1), 1 - (p - mn) / sp]);
}

// each person's signal results in recency order (newest first) → 'w'/'l'
function resultsOf(id) {
  const out = [];
  for (const p of posts) {
    if (p.who !== id) continue;
    for (const s of p.signals) {
      const pl = pnl(s, 'latest');
      if (pl != null) out.push(pl >= 0 ? 'w' : 'l');
    }
  }
  return out;
}

function verdictOf(sig) {
  const pl = pnl(sig, 'latest');
  if (pl == null) return { t: '追蹤中', c: 'wait', stamp: 'LIVE' };
  if (sig.type === 'sell') return pl >= 0 ? { t: '賣對了', c: 'win', stamp: 'WIN' } : { t: '賣早了', c: 'lose', stamp: 'MISS' };
  return pl >= 0 ? { t: '跟單賺', c: 'win', stamp: 'WIN' } : { t: '住套房', c: 'lose', stamp: 'LOSS' };
}

/* ---------- sparkline ---------- */
function Spark({ sig, w = 200, h = 30 }) {
  const pts = useMemo(() => sparkPoints(sig), [sig.ticker, sig.type]);
  const win = (pnl(sig, 'latest') ?? 0) >= 0;
  const col = win ? 'var(--win)' : 'var(--loss)';
  const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${(x * w).toFixed(1)},${(3 + y * (h - 6)).toFixed(1)}`).join(' ');
  const [lx, ly] = pts[pts.length - 1];
  return (
    <svg className="spark" width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ height: h }}>
      <path d={d} fill="none" stroke={col} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx * w} cy={3 + ly * (h - 6)} r="2.6" fill={col} />
    </svg>
  );
}

/* ---------- standings ---------- */
function StandingRow({ id, rank, active, onClick, spark }) {
  const p = people[id];
  const dnp = p.cumReturn == null;
  const form = resultsOf(id);
  const W = dnp ? 0 : Math.round(p.signals * p.winRate);
  const L = dnp ? 0 : p.signals - W;
  return (
    <div
      className={'st-row' + (rank === 1 && !dnp ? ' rank-1' : '') + (active ? ' is-active' : '') + (dnp ? ' dnp' : '')}
      style={{ '--hue': p.hue }} onClick={onClick}
    >
      <div>
        {dnp ? <span className="rank-tag">DNP</span>
          : <span className="rank">{rank}</span>}
      </div>
      <div className="player">
        <span className="jersey">{p.initial}</span>
        <div className="player-meta">
          <div className="player-name">{p.name}</div>
          <div className="player-blurb">{p.blurb}</div>
        </div>
      </div>
      <div className="st-cell-win">
        {dnp ? <span className="record"><span className="sub">未上場</span></span>
          : <span className="record"><span className="w">{W}</span><span className="sep">–</span><span className="l">{L}</span><span className="sub">命中 / 槓龜</span></span>}
      </div>
      <div className="st-cell-pct">
        {dnp ? <span className="winpct" style={{ color: 'var(--ink-3)' }}>—</span>
          : <span className="winpct">{Math.round(p.winRate * 100)}%</span>}
      </div>
      <div className="score">
        {dnp ? <><span className="big" style={{ color: 'var(--ink-3)', fontSize: 22 }}>—</span><span className="cap">純分享錶圈</span></>
          : <><span className={'big ' + (p.cumReturn >= 0 ? 'up' : 'down')}>{fmtPct(p.cumReturn)}</span><span className="cap">累積跟單損益</span></>}
      </div>
      <div className="st-cell-form">
        <div className="form">
          {form.length === 0 ? <span className="form-empty">尚無喊單</span>
            : form.slice(0, 5).map((r, i) => (
              <span key={i} className={'form-dot ' + r}>{r === 'w' ? 'W' : 'L'}</span>
            ))}
        </div>
      </div>
    </div>
  );
}

/* ---------- play-by-play ---------- */
function ResultBlock({ sig, spark }) {
  const v = verdictOf(sig);
  const pl = pnl(sig, 'latest');
  const Col = ({ k, h }) => {
    const val = pnl(sig, h);
    return (
      <div className="res-col">
        <span className="k">{k}</span>
        {val == null ? <span className="v wait">追蹤中</span> : <span className={'v ' + (val >= 0 ? 'up' : 'down')}>{fmtPct(val)}</span>}
      </div>
    );
  };
  return (
    <div className="res-item">
      <div className="res-tk">
        <span className="sym">{sig.ticker}</span>
        <span className="mk">{sig.market}</span>
        <span className="co">{sig.company}</span>
      </div>
      <div className="verdict-line">
        <span className={'stamp ' + v.c}>{v.stamp}</span>
        <span className={'verdict ' + v.c}>{v.t}</span>
      </div>
      <div className={'pnl-big ' + (pl == null ? '' : pl >= 0 ? 'up' : 'down')}>{pl == null ? '—' : fmtPct(pl)}</div>
      <div className="res-cols"><Col k="7日" h="d7" /><Col k="1月" h="m1" /></div>
      {spark && <Spark sig={sig} />}
    </div>
  );
}

function Play({ post, spark }) {
  const [open, setOpen] = useState(false);
  const sigs = post.signals;
  const has = sigs.length > 0;
  const long = (post.body || '').length > 110 || post.kind === 'podcast';
  // row accent: win if any winning, else loss if any losing, else wait/none
  let cls = 'none';
  if (has) {
    const pls = sigs.map((s) => pnl(s, 'latest'));
    if (pls.some((x) => x != null && x >= 0)) cls = 'win';
    else if (pls.some((x) => x != null && x < 0)) cls = 'loss';
    else cls = 'wait';
  }
  const main = has ? sigs[0] : null;

  return (
    <div className={'play ' + cls} style={{ '--hue': people[post.who].hue }}>
      <div className="fixture">
        <div className="fx-top">
          <span className="jersey" style={{ width: 32, height: 32, fontSize: 15 }}>{people[post.who].initial}</span>
          <div>
            <div className="fx-name">{people[post.who].name}</div>
            <div className="fx-time">{post.time}</div>
          </div>
        </div>
        {has
          ? <span className={'fx-badge ' + (isLong(main) ? 'long' : 'sell')}>{isLong(main) ? '喊多' : '喊賣'} {main.ticker}{sigs.length > 1 ? ` +${sigs.length - 1}` : ''}</span>
          : <span className="fx-badge none">場外發言</span>}
      </div>

      <div className="play-body">
        {post.title && (
          <h3 className="play-title">{post.kind === 'podcast' && <span className="kind" style={{ marginRight: 8 }}>🎙 PODCAST</span>}{post.title}</h3>
        )}
        <p className={'play-text' + (long && !open ? ' clamp' : '')}>{post.body}</p>
        {long && <button className="more" onClick={() => setOpen(!open)}>{open ? '收合 ▲' : '展開全文 ▼'}</button>}
        <div className="play-foot">
          {has
            ? sigs.map((s, i) => (
                <span key={i} className={'tag ' + (isLong(s) ? 'long' : 'sell')}>
                  {isLong(s) ? '看多' : '賣出'}<span className="tk">{s.ticker}</span><span className="mk">{s.market}</span>
                </span>
              ))
            : <span style={{ fontSize: 12.5, color: 'var(--ink-3)', fontStyle: 'italic' }}>未偵測到個股買賣訊號</span>}
          <a className="src" href="#" onClick={(e) => e.preventDefault()}>{post.source} ↗</a>
        </div>
      </div>

      {has
        ? <div className="result">{sigs.map((s, i) => <ResultBlock key={i} sig={s} spark={spark} />)}</div>
        : <div className="result"><div className="res-none"><span className="big">NO CALL</span><span className="sub">這則沒有喊單，不列入戰績</span></div></div>}
    </div>
  );
}

/* ---------- app ---------- */
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "night": "off",
  "accent": "#D14B2A",
  "spark": true,
  "showForm": true
}/*EDITMODE-END*/;

const ACCENTS = {
  "#D14B2A": [30, 0.17, 0.66],   // scoreboard red
  "#1F7A4D": [152, 0.13, 0.55],  // turf green
  "#2B5FCC": [262, 0.16, 0.56],  // electric blue
  "#C98A14": [85, 0.13, 0.66],   // amber LED
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [person, setPerson] = useState('all');
  const [signalOnly, setSignalOnly] = useState(false);

  const a = ACCENTS[t.accent] || ACCENTS["#D14B2A"];
  const rootStyle = { '--accent': `oklch(${a[2]} ${a[1]} ${a[0]})`, color: 'var(--ink)', background: 'var(--field)', minHeight: '100vh' };

  const ranked = useMemo(() => {
    const ids = Object.keys(people);
    const scored = ids.filter((id) => people[id].cumReturn != null).sort((x, y) => people[y].cumReturn - people[x].cumReturn);
    const dnp = ids.filter((id) => people[id].cumReturn == null);
    return [...scored, ...dnp];
  }, []);

  const counts = useMemo(() => {
    const c = {}; for (const id of Object.keys(people)) c[id] = posts.filter((p) => p.who === id).length; return c;
  }, []);

  const visible = posts.filter((p) => (person === 'all' || p.who === person) && (!signalOnly || p.signals.length > 0));

  return (
    <div data-night={t.night} style={rootStyle}>
      <header className="scorebar">
        <div className="scorebar-in">
          <div className="wordmark">
            <span className="zh">對帳時刻</span>
            <span className="en">STOCK GURU SCOREBOARD</span>
          </div>
          <span className="live-pill"><span className="live-dot"></span>本季 LIVE</span>
        </div>
      </header>

      <main className="wrap">
        <div className="sec-head">
          <h2>戰績排行榜</h2>
          <span className="en">STANDINGS</span>
          <span className="note">依累積跟單損益排名 · 點名字可篩選下方喊單</span>
        </div>

        <div className="standings">
          <div className="st-row st-head">
            <div>名次</div><div>老師</div>
            <div className="col-win">戰績</div>
            <div className="col-pct">命中率</div>
            <div>累積損益</div>
            <div className="col-form">近 5 場</div>
          </div>
          <div className="st-body">
            {ranked.map((id, i) => (
              <StandingRow key={id} id={id} rank={i + 1}
                active={person === id}
                onClick={() => setPerson(person === id ? 'all' : id)}
                spark={t.spark} />
            ))}
          </div>
        </div>

        <div className="sec-head">
          <h2>喊單實況</h2>
          <span className="en">PLAY-BY-PLAY</span>
          <span className="note">每則貼文逐筆判定，AI 標記喊了哪些股票</span>
        </div>

        <div className="filters">
          <button className={'tab' + (person === 'all' ? ' on' : '')} onClick={() => setPerson('all')}>全部</button>
          {Object.keys(people).map((id) => (
            <button key={id} className={'tab' + (person === id ? ' on' : '')} style={{ '--hue': people[id].hue }}
              onClick={() => setPerson(person === id ? 'all' : id)}>
              <span className="jd">{people[id].initial}</span>{people[id].name}<span className="cnt">{counts[id]}</span>
            </button>
          ))}
          <button className={'tab toggle' + (signalOnly ? ' on' : '')} onClick={() => setSignalOnly(!signalOnly)}>只看喊單</button>
        </div>

        <div className="pbp">
          {visible.map((p) => <Play key={p.id} post={p} spark={t.spark} />)}
          {visible.length === 0 && <div style={{ padding: '40px', textAlign: 'center', color: 'var(--ink-3)', fontStyle: 'italic' }}>這個篩選條件下沒有貼文。</div>}
        </div>
      </main>

      <TweaksPanel>
        <TweakSection label="賽場" />
        <TweakRadio label="場館燈光" value={t.night}
          options={[{ value: 'off', label: '日場' }, { value: 'on', label: '夜場' }]}
          onChange={(v) => setTweak('night', v)} />
        <TweakColor label="主隊色" value={t.accent} options={Object.keys(ACCENTS)} onChange={(v) => setTweak('accent', v)} />
        <TweakSection label="顯示" />
        <TweakToggle label="走勢小圖" value={t.spark} onChange={(v) => setTweak('spark', v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
