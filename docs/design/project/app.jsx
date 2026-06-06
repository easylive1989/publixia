/* global React, ReactDOM, useTweaks, TweaksPanel, TweakSection, TweakRadio, TweakToggle, TweakColor */
const { useState, useMemo } = React;
const { people, posts } = window.TRACKER_DATA;

/* ---------------- helpers ---------------- */
const pHue = (id) => people[id].hue;
const isLong = (s) => s.type === 'long' || s.type === 'buy';
const fmtPct = (v) => (v > 0 ? '+' : '') + v.toFixed(1) + '%';

// copy-trade P&L for a given horizon ('latest' | 'd7' | 'm1')
function pnl(sig, horizon) {
  const raw = sig.perf[horizon];
  if (raw == null) return null;
  return isLong(sig) ? raw : -raw;
}

// deterministic pseudo-random series → sparkline points (0..1)
function sparkPoints(sig) {
  let seed = [...(sig.ticker + sig.type)].reduce((a, c) => a + c.charCodeAt(0), 0);
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  const n = 26;
  const end = pnl(sig, 'latest') ?? (isLong(sig) ? 2 : -2);
  const arr = [];
  let v = 0;
  for (let i = 0; i < n; i++) { v += (rnd() - 0.5) * 3.2; arr.push(v); }
  for (let i = 0; i < n; i++) arr[i] += (end / 8) * (i / (n - 1)) * (i / (n - 1));
  const mn = Math.min(...arr), mx = Math.max(...arr), span = (mx - mn) || 1;
  return arr.map((p, i) => [i / (n - 1), 1 - (p - mn) / span]);
}

/* ---------------- atoms ---------------- */
function Avatar({ id, sm }) {
  const p = people[id];
  return (
    <span className={'avatar' + (sm ? ' sm' : '')} style={{ '--person-hue': p.hue }} aria-hidden="true">
      {p.initial}
    </span>
  );
}

function Sparkline({ sig, width = 240, height = 34 }) {
  const pts = useMemo(() => sparkPoints(sig), [sig.ticker, sig.type]);
  const win = (pnl(sig, 'latest') ?? 0) >= 0;
  const color = win ? 'var(--profit)' : 'var(--loss)';
  const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${(x * width).toFixed(1)},${(4 + y * (height - 8)).toFixed(1)}`).join(' ');
  const [lx, ly] = pts[pts.length - 1];
  const areaD = d + ` L${width},${height} L0,${height} Z`;
  const gid = 'g_' + sig.ticker + sig.type;
  return (
    <svg className="spark" width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: 'block', height }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.16" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#${gid})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx * width} cy={4 + ly * (height - 8)} r="2.6" fill={color} />
    </svg>
  );
}

/* ---------------- perf panel ---------------- */
function PerfItem({ sig, mode, spark }) {
  const usePnl = mode === 'pnl';
  const headline = usePnl ? pnl(sig, 'latest') : sig.perf.latest;
  const win = (pnl(sig, 'latest') ?? 0) >= 0;
  const cls = headline == null ? '' : headline >= 0 ? 'up' : 'down';
  const arrow = isLong(sig) ? '▲' : '▼';
  const arrowCol = isLong(sig) ? 'var(--profit)' : 'var(--loss)';

  const verdict = headline == null
    ? { t: '追蹤中', c: 'wait' }
    : usePnl
      ? (win ? { t: sig.type === 'sell' ? '賣對了' : '跟單賺', c: 'win' } : { t: sig.type === 'sell' ? '賣早了' : '住套房', c: 'lose' })
      : (headline >= 0 ? { t: '上漲', c: 'win' } : { t: '下跌', c: 'lose' });

  const Col = ({ k, h }) => {
    const v = usePnl ? pnl(sig, h) : sig.perf[h];
    return (
      <div className="perf-col">
        <span className="k">{k}</span>
        {v == null ? <span className="v wait">追蹤中</span>
          : <span className={'v ' + (v >= 0 ? 'up' : 'down')}>{fmtPct(v)}</span>}
      </div>
    );
  };

  return (
    <div className="perf-item">
      <div>
        <div className="perf-tk">
          <span className="arrow" style={{ color: arrowCol }}>{arrow}</span>
          <span className="sym">{sig.ticker}</span>
          <span className="mk">{sig.market}</span>
        </div>
        <div className="perf-co">{sig.company}{sig.callPrice ? ` · 喊在 ${sig.callPrice}` : ''}</div>
      </div>
      <div>
        <div className="perf-label">{usePnl ? '跟單損益' : '個股漲跌'}</div>
        <div className="perf-pnl">
          <span className={'big ' + cls}>{headline == null ? '—' : fmtPct(headline)}</span>
          <span className={'verdict ' + verdict.c}>{verdict.t}</span>
        </div>
      </div>
      <div className="perf-cols">
        <Col k="7 日" h="d7" />
        <Col k="1 月" h="m1" />
      </div>
      {spark && <Sparkline sig={sig} />}
    </div>
  );
}

/* ---------------- post card ---------------- */
function PostCard({ post, mode, spark }) {
  const [open, setOpen] = useState(false);
  const long = (post.body || '').length > 120 || post.kind === 'podcast';
  const hasPerf = post.signals.length > 0;

  return (
    <div className={'row' + (hasPerf ? ' has-signal' : '')} style={{ '--person-hue': pHue(post.who) }}>
      <span className="node"></span>
      <div className="card">
        <div className={'card-grid' + (hasPerf ? ' with-perf' : '')}>
          <div className="post">
            <div className="post-head">
              <Avatar id={post.who} sm />
              <span className="post-name">{people[post.who].name}</span>
              <span className="post-bull">·</span>
              <span className="post-meta">{post.time}</span>
              {post.kind === 'podcast' && <span className="kind-badge">🎙 Podcast</span>}
              <a className="source-link" href="#" onClick={(e) => e.preventDefault()}>
                {post.source} <span aria-hidden="true">↗</span>
              </a>
            </div>

            {post.title && <h3 className="post-title">{post.title}</h3>}
            <p className={'post-body' + (long && !open ? ' clamped' : '')}>{post.body}</p>
            {long && (
              <button className="read-more" onClick={() => setOpen(!open)}>
                {open ? '收合' : '展開全文'}
              </button>
            )}

            <div className="post-foot">
              {hasPerf ? post.signals.map((s, i) => (
                <span key={i} className={'sigchip ' + (isLong(s) ? 'long' : 'sell')}>
                  {isLong(s) ? '看多' : '賣出'}
                  <span className="tk">{s.ticker}</span>
                  <span className="mk">{s.market}</span>
                </span>
              )) : (
                <span className="no-signal">未偵測到個股買賣訊號</span>
              )}
            </div>
          </div>

          {hasPerf && (
            <div className="perf">
              {post.signals.map((s, i) => <PerfItem key={i} sig={s} mode={mode} spark={spark} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------------- leaderboard ---------------- */
function LeaderCard({ id, active, onClick }) {
  const p = people[id];
  const hasStats = p.cumReturn != null;
  const ret = p.cumReturn;
  return (
    <button
      className={'lb' + (active ? ' active' : '')}
      style={{ '--person-hue': p.hue, '--person': `oklch(0.62 0.16 ${p.hue})` }}
      onClick={onClick}
    >
      <div className="lb-top">
        <Avatar id={id} />
        <div>
          <div className="lb-name">{p.name}</div>
          <div className="lb-blurb">{p.blurb}</div>
        </div>
      </div>
      {hasStats ? (
        <>
          <div className="lb-stats">
            <div className="lb-stat">
              <span className="k">命中率</span>
              <span className="v num">{Math.round(p.winRate * 100)}%</span>
            </div>
            <div className="lb-stat">
              <span className="k">累積跟單</span>
              <span className={'v num ' + (ret >= 0 ? 'up' : 'down')}>{fmtPct(ret)}</span>
            </div>
          </div>
          <div className="lb-track">
            <i style={{
              width: Math.min(100, Math.abs(ret) * 1.6 + 14) + '%',
              background: ret >= 0 ? 'var(--profit)' : 'var(--loss)',
            }}></i>
          </div>
        </>
      ) : (
        <div className="lb-empty">0 筆有效訊號 · 純分享錶圈</div>
      )}
    </button>
  );
}

/* ---------------- app ---------------- */
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "paper",
  "accent": "#D98A3D",
  "density": "regular",
  "pnlMode": "pnl",
  "spark": true,
  "board": true
}/*EDITMODE-END*/;

const ACCENTS = {
  "#D98A3D": [58, 0.145, 0.70, 0.42, 0.12],   // amber
  "#2F8F73": [165, 0.10, 0.60, 0.40, 0.09],   // teal
  "#5B6BD6": [278, 0.13, 0.58, 0.46, 0.11],   // indigo
  "#C9577E": [358, 0.13, 0.62, 0.46, 0.11],   // rose
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [person, setPerson] = useState('all');
  const [signalOnly, setSignalOnly] = useState(false);

  const a = ACCENTS[t.accent] || ACCENTS["#D98A3D"];
  const rootStyle = {
    '--accent': `oklch(${a[2]} ${a[1]} ${a[0]})`,
    '--accent-ink': `oklch(${a[3]} ${a[4]} ${a[0]})`,
    color: 'var(--ink)', background: 'var(--bg)', minHeight: '100vh',
  };

  const counts = useMemo(() => {
    const c = {};
    for (const id of Object.keys(people)) c[id] = posts.filter((p) => p.who === id).length;
    return c;
  }, []);

  const visible = posts.filter((p) =>
    (person === 'all' || p.who === person) &&
    (!signalOnly || p.signals.length > 0)
  );

  return (
    <div data-theme={t.theme} data-density={t.density} style={rootStyle}>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <div className="zh">對帳<em>時刻</em></div>
            <div className="en">Stock Guru Scoreboard</div>
          </div>
          <div className="tagline">追蹤社群名人的<br /><b>一買一賣</b>，與後續真實成效</div>
        </div>
      </header>

      <main className="wrap">
        <div className="page-head">
          <h1>動態時間軸</h1>
          <p>所有追蹤對象的貼文混合排序，AI 標出他們喊了哪些股票，並換算成「如果你當時跟單」的真實損益。篩選條件可以組合。</p>
        </div>

        {t.board && (
          <div className="board">
            {Object.keys(people).map((id) => (
              <LeaderCard
                key={id}
                id={id}
                active={person === id}
                onClick={() => setPerson(person === id ? 'all' : id)}
              />
            ))}
          </div>
        )}

        <div className="filters">
          <button className={'chip' + (person === 'all' ? ' on' : '')} onClick={() => setPerson('all')}>全部</button>
          {Object.keys(people).map((id) => (
            <button
              key={id}
              className={'chip' + (person === id ? ' on' : '')}
              style={{ '--person-hue': people[id].hue }}
              onClick={() => setPerson(person === id ? 'all' : id)}
            >
              <span className="dot">{people[id].initial}</span>
              {people[id].name}
              <span className="cnt">{counts[id]}</span>
            </button>
          ))}
          <span className="sep"></span>
          <button className={'chip toggle' + (signalOnly ? ' on' : '')} onClick={() => setSignalOnly(!signalOnly)}>
            📈 有提到股票
          </button>
        </div>

        <div className="timeline">
          {visible.map((p) => <PostCard key={p.id} post={p} mode={t.pnlMode} spark={t.spark} />)}
          {visible.length === 0 && (
            <div style={{ color: 'var(--ink-3)', fontStyle: 'italic', padding: '40px 0', textAlign: 'center' }}>
              這個篩選條件下沒有貼文。
            </div>
          )}
        </div>
      </main>

      <TweaksPanel>
        <TweakSection label="外觀" />
        <TweakRadio label="主題" value={t.theme}
          options={[{ value: 'paper', label: '暖紙' }, { value: 'slate', label: '冷灰' }, { value: 'terminal', label: '終端機' }]}
          onChange={(v) => setTweak('theme', v)} />
        <TweakColor label="重點色" value={t.accent}
          options={Object.keys(ACCENTS)}
          onChange={(v) => setTweak('accent', v)} />
        <TweakRadio label="密度" value={t.density}
          options={[{ value: 'compact', label: '緊湊' }, { value: 'regular', label: '舒適' }]}
          onChange={(v) => setTweak('density', v)} />

        <TweakSection label="內容" />
        <TweakRadio label="成效呈現" value={t.pnlMode}
          options={[{ value: 'pnl', label: '跟單損益' }, { value: 'raw', label: '個股漲跌' }]}
          onChange={(v) => setTweak('pnlMode', v)} />
        <TweakToggle label="走勢小圖" value={t.spark} onChange={(v) => setTweak('spark', v)} />
        <TweakToggle label="戰績總覽" value={t.board} onChange={(v) => setTweak('board', v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
