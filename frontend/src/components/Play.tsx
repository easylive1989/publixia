import { useState } from 'react';
import { asUtc, relativeTime } from '@/lib/relative-time';
import { initialOf, personHue } from '@/lib/person-hue';
import { fmtPct, isCall, pnl, side, verdict } from '@/lib/verdict';
import type { TimelinePost, Trade } from '@/hooks/usePeople';

function PctCol({ k, t, w }: { k: string; t: Trade; w: 'pct_7d' | 'pct_1m' }) {
  const val = pnl(t, w);
  return (
    <div className="res-col">
      <span className="k">{k}</span>
      {val == null ? (
        <span className="v wait">追蹤中</span>
      ) : (
        <span className={'v ' + (val >= 0 ? 'up' : 'down')}>{fmtPct(val)}</span>
      )}
    </div>
  );
}

function ResultBlock({ t }: { t: Trade }) {
  const v = verdict(t);
  const pl = pnl(t, 'pct_latest');
  return (
    <div className="res-item">
      <div className="res-tk">
        <span className="sym">{t.ticker ?? t.raw_symbol}</span>
        {t.market && <span className="mk">{t.market}</span>}
        {t.stock_name && <span className="co">{t.stock_name}</span>}
      </div>
      <div className="verdict-line">
        <span className={'stamp ' + v.cls}>{v.stamp}</span>
        <span className={'verdict ' + v.cls}>{v.label}</span>
      </div>
      <div className={'pnl-big ' + (pl == null ? '' : pl >= 0 ? 'up' : 'down')}>
        {pl == null ? '—' : fmtPct(pl)}
      </div>
      <div className="res-cols">
        <PctCol k="7日" t={t} w="pct_7d" />
        <PctCol k="1月" t={t} w="pct_1m" />
      </div>
    </div>
  );
}

export function Play({ post, allKeys }: { post: TimelinePost; allKeys: string[] }) {
  const [open, setOpen] = useState(false);
  const calls = post.trades.filter(isCall);
  const has = calls.length > 0;
  const isPodcast = post.platform === 'podcast';
  const long = (post.content || '').length > 110 || isPodcast;
  const hue = personHue(post.person.person_key, allKeys);
  const posted = post.posted_at ? asUtc(post.posted_at) : null;
  const main = has ? calls[0] : null;

  let cls = 'none';
  if (has) {
    const pls = calls.map((t) => pnl(t, 'pct_latest'));
    if (pls.some((x) => x != null && x >= 0)) cls = 'win';
    else if (pls.some((x) => x != null && x < 0)) cls = 'loss';
    else cls = 'wait';
  }

  return (
    <div className={'play ' + cls} style={{ '--hue': hue } as React.CSSProperties}>
      <div className="fixture">
        <div className="fx-top">
          <span className="jersey" style={{ width: 32, height: 32, fontSize: 15 }}>
            {initialOf(post.person.display_name)}
          </span>
          <div>
            <div className="fx-name">{post.person.display_name}</div>
            <div className="fx-time">{posted ? relativeTime(posted) : '時間未知'}</div>
          </div>
        </div>
        {has && main ? (
          <span className={'fx-badge ' + (side(main.direction) === 'long' ? 'long' : 'sell')}>
            {side(main.direction) === 'long' ? '喊多' : '喊賣'} {main.ticker ?? main.raw_symbol}
            {calls.length > 1 ? ` +${calls.length - 1}` : ''}
          </span>
        ) : (
          <span className="fx-badge none">場外發言</span>
        )}
      </div>

      <div className="play-body">
        {isPodcast && post.title && (
          <h3 className="play-title">
            <span className="kind" style={{ marginRight: 8 }}>🎙 PODCAST</span>
            {post.title}
          </h3>
        )}
        <p className={'play-text' + (long && !open ? ' clamp' : '')}>{post.content}</p>
        {long && (
          <button className="more" onClick={() => setOpen(!open)}>
            {open ? '收合 ▲' : '展開全文 ▼'}
          </button>
        )}
        <div className="play-foot">
          {has ? (
            calls.map((t, i) => (
              <span key={i} className={'tag ' + (side(t.direction) === 'long' ? 'long' : 'sell')}>
                {side(t.direction) === 'long' ? '看多' : '賣出'}
                <span className="tk">{t.ticker ?? t.raw_symbol}</span>
                {t.market && <span className="mk">{t.market}</span>}
              </span>
            ))
          ) : (
            <span className="no-call-text">未偵測到個股買賣訊號</span>
          )}
          <a className="src" href={post.url} target="_blank" rel="noopener noreferrer">
            {isPodcast ? '聽這集' : '看原文'} ↗
          </a>
        </div>
      </div>

      {has ? (
        <div className="result">
          {calls.map((t, i) => (
            <ResultBlock key={i} t={t} />
          ))}
        </div>
      ) : (
        <div className="result">
          <div className="res-none">
            <span className="big">NO CALL</span>
            <span className="sub">這則沒有喊單，不列入戰績</span>
          </div>
        </div>
      )}
    </div>
  );
}
