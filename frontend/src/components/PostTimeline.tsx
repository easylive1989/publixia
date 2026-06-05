import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { TradeChip } from '@/components/TradeChip';
import { relativeTime, asUtc } from '@/lib/relative-time';
import { cn } from '@/lib/utils';
import { personColor } from '@/lib/person-color';
import type { Post, PostAuthor } from '@/hooks/usePeople';

type TimelineItem = Post & { person?: PostAuthor };

function PostItem({ post, index }: { post: TimelineItem; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = post.content.length > 140;
  const posted = post.posted_at ? asUtc(post.posted_at) : null;
  const author = post.person;

  // distinct stocks mentioned in this post, for the right-side annotation rail.
  // Each shows its code + name + 7d/1m return from the post's entry time.
  const symbols: {
    key: string;
    code: string | null;
    name: string;
    pctLatest: number | null;
    pct7: number | null;
    pct1m: number | null;
    priceStatus: string | null;
  }[] = [];
  for (const t of post.trades) {
    const key = t.ticker ?? t.raw_symbol;
    if (!key || symbols.some((s) => s.key === key)) continue;
    symbols.push({
      key,
      code: t.ticker,
      name: t.stock_name ?? t.raw_symbol,
      pctLatest: t.pct_latest,
      pct7: t.pct_7d,
      pct1m: t.pct_1m,
      priceStatus: t.price_status,
    });
  }

  return (
    <li className="relative animate-rise pl-8" style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}>
      {/* timeline node + rule */}
      <span className="absolute left-0 top-2 size-3 -translate-x-[5px] rounded-full border-2 border-background bg-primary" />

      <div className="flex gap-4 rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-center justify-between gap-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              {author && (
                <Link
                  to={`/people/${author.person_key}`}
                  className={cn(
                    'inline-flex items-center gap-1.5 font-semibold hover:underline',
                    personColor(author.person_key).name,
                  )}
                >
                  <span
                    className={cn(
                      'flex size-5 items-center justify-center rounded-full text-[10px] font-semibold text-white',
                      personColor(author.person_key).avatar,
                    )}
                  >
                    {author.display_name.slice(0, 1)}
                  </span>
                  {author.display_name}
                </Link>
              )}
              {author && <span aria-hidden>·</span>}
              <time dateTime={posted ?? undefined} title={posted ? new Date(posted).toLocaleString('zh-TW') : ''}>
                {posted ? relativeTime(posted) : '時間未知'}
              </time>
            </div>
            <a
              href={post.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-mono uppercase tracking-wide hover:text-foreground"
            >
              看原文 <ExternalLink className="size-3" />
            </a>
          </div>

          <p className={cn('whitespace-pre-wrap text-[15px] leading-relaxed', !expanded && isLong && 'line-clamp-3')}>
            {post.content}
          </p>
          {isLong && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="mt-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              {expanded ? '收合' : '展開全文'}
            </button>
          )}

          {post.trades.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2 border-t border-dashed border-border pt-4">
              {post.trades.map((t, i) => (
                <TradeChip key={`${t.raw_symbol}-${t.direction}-${i}`} trade={t} />
              ))}
            </div>
          ) : (
            post.extraction_status === 'done' && (
              <div className="mt-3 text-xs italic text-muted-foreground">未偵測到個股買賣訊號</div>
            )
          )}
        </div>

        {/* right-side stock annotation: code + name + 最新/7日/1月 return */}
        {symbols.length > 0 && (
          <aside className="flex w-32 shrink-0 flex-col items-end gap-4 border-l border-dashed border-border pl-4">
            {symbols.map((s) => (
              <span key={s.key} className="flex flex-col items-end leading-tight">
                {s.code && (
                  <span className="font-mono text-lg font-bold text-foreground">{s.code}</span>
                )}
                <span className="text-right text-sm text-muted-foreground">{s.name}</span>
                <span className="mt-1.5 flex flex-col items-end gap-1">
                  <PctRow label="最新" pct={s.pctLatest} />
                  <PctRow label="7日" pct={s.pct7} />
                  <PctRow label="1月" pct={s.pct1m} />
                </span>
              </span>
            ))}
          </aside>
        )}
      </div>
    </li>
  );
}

// 紅漲綠跌 (Taiwan convention): up → --sell (red), down → --buy (green).
function PctRow({ label, pct }: { label: string; pct: number | null }) {
  if (pct == null) {
    return (
      <span className="font-mono text-xs text-muted-foreground/70">
        {label} <span className="italic">追蹤中</span>
      </span>
    );
  }
  const cls =
    pct > 0
      ? 'text-[hsl(var(--sell))]'
      : pct < 0
        ? 'text-[hsl(var(--buy))]'
        : 'text-muted-foreground';
  return (
    <span className="font-mono text-xs">
      <span className="text-muted-foreground">{label} </span>
      <span className={cn('font-semibold', cls)}>
        {pct > 0 ? '+' : ''}
        {(pct * 100).toFixed(1)}%
      </span>
    </span>
  );
}

export function PostTimeline({ posts }: { posts: TimelineItem[] }) {
  if (posts.length === 0) {
    return <p className="py-16 text-center text-muted-foreground">目前還沒有抓到貼文。</p>;
  }
  return (
    <ol className="relative space-y-5 border-l border-border pl-0">
      {posts.map((p, i) => (
        <PostItem key={p.id} post={p} index={i} />
      ))}
    </ol>
  );
}
