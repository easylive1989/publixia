import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { TradeChip } from '@/components/TradeChip';
import { relativeTime, asUtc } from '@/lib/relative-time';
import { cn } from '@/lib/utils';
import type { Post, PostAuthor } from '@/hooks/usePeople';

type TimelineItem = Post & { person?: PostAuthor };

function PostItem({ post, index }: { post: TimelineItem; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = post.content.length > 140;
  const posted = post.posted_at ? asUtc(post.posted_at) : null;
  const author = post.person;

  return (
    <li className="relative animate-rise pl-8" style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}>
      {/* timeline node + rule */}
      <span className="absolute left-0 top-2 size-3 -translate-x-[5px] rounded-full border-2 border-background bg-primary" />

      <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="mb-2 flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            {author && (
              <Link
                to={`/people/${author.person_key}`}
                className="inline-flex items-center gap-1.5 font-medium text-foreground hover:underline"
              >
                <span className="flex size-5 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
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
    </li>
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
