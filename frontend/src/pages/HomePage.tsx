import { useState } from 'react';
import { Masthead } from '@/components/Masthead';
import { PostTimeline } from '@/components/PostTimeline';
import { usePeople, useTimeline } from '@/hooks/usePeople';
import { cn } from '@/lib/utils';

export default function HomePage() {
  const people = usePeople();
  const timeline = useTimeline();
  const [selected, setSelected] = useState<string | null>(null);

  const posts = timeline.data ?? [];
  const filtered = selected ? posts.filter((p) => p.person.person_key === selected) : posts;

  return (
    <div className="min-h-screen">
      <Masthead />
      <main className="container max-w-3xl py-10">
        <div className="mb-6">
          <h1 className="font-display text-2xl font-semibold">動態時間軸</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            所有追蹤對象的貼文混合排序,AI 標出他們買賣了哪些股票。點下方人物可只看他的貼文。
          </p>
        </div>

        {/* 人物篩選器(點了篩選下方動態,不換頁) */}
        {people.data && people.data.length > 0 && (
          <div className="mb-8 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">追蹤中:</span>
            <FilterChip label="全部" active={selected === null} onClick={() => setSelected(null)} />
            {people.data.map((p) => (
              <FilterChip
                key={p.person_key}
                label={p.display_name}
                count={p.trade_count}
                initial={p.display_name.slice(0, 1)}
                active={selected === p.person_key}
                onClick={() => setSelected((cur) => (cur === p.person_key ? null : p.person_key))}
              />
            ))}
          </div>
        )}

        {timeline.isLoading && <p className="py-16 text-center text-muted-foreground">載入中…</p>}
        {timeline.isError && <p className="py-16 text-center text-[hsl(var(--sell))]">載入失敗,請稍後再試。</p>}
        {timeline.data && <PostTimeline posts={filtered} />}
      </main>
    </div>
  );
}

function FilterChip({
  label,
  count,
  initial,
  active,
  onClick,
}: {
  label: string;
  count?: number;
  initial?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors',
        active
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border bg-secondary text-foreground hover:bg-accent',
      )}
    >
      {initial && (
        <span
          className={cn(
            'flex size-5 items-center justify-center rounded-full text-[10px] font-semibold',
            active ? 'bg-primary-foreground text-primary' : 'bg-primary text-primary-foreground',
          )}
        >
          {initial}
        </span>
      )}
      {label}
      {count !== undefined && (
        <span className={cn('font-mono text-xs', active ? 'text-primary-foreground/80' : 'text-muted-foreground')}>
          {count}
        </span>
      )}
    </button>
  );
}
