import { useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { Masthead } from '@/components/Masthead';
import { PostTimeline } from '@/components/PostTimeline';
import { usePeople, useTimeline } from '@/hooks/usePeople';
import { personColor } from '@/lib/person-color';
import { cn } from '@/lib/utils';

export default function HomePage() {
  const people = usePeople();
  const timeline = useTimeline();
  const [selected, setSelected] = useState<string | null>(null);
  const [onlyStocks, setOnlyStocks] = useState(false);

  const posts = timeline.data ?? [];
  const filtered = posts.filter(
    (p) =>
      (selected === null || p.person.person_key === selected) &&
      (!onlyStocks || p.trades.length > 0),
  );

  return (
    <div className="min-h-screen">
      <Masthead />
      <main className="container max-w-3xl py-10">
        <div className="mb-6">
          <h1 className="font-display text-2xl font-semibold">動態時間軸</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            所有追蹤對象的貼文混合排序,AI 標出他們買賣了哪些股票。篩選條件可以組合。
          </p>
        </div>

        {/* 可組合的篩選器:人物(單選)＋ 有提到股票(開關) */}
        <div className="mb-8 flex flex-wrap items-center gap-2">
          <FilterChip label="全部" active={selected === null} onClick={() => setSelected(null)} />
          {(people.data ?? []).map((p) => (
            <FilterChip
              key={p.person_key}
              label={p.display_name}
              initial={p.display_name.slice(0, 1)}
              avatarClass={personColor(p.person_key).avatar}
              count={p.trade_count}
              active={selected === p.person_key}
              onClick={() => setSelected((cur) => (cur === p.person_key ? null : p.person_key))}
            />
          ))}
          <span className="mx-1 h-5 w-px bg-border" aria-hidden />
          <FilterChip
            label="有提到股票"
            icon={<TrendingUp className="size-3.5" />}
            active={onlyStocks}
            onClick={() => setOnlyStocks((v) => !v)}
          />
        </div>

        {timeline.isLoading && <p className="py-16 text-center text-muted-foreground">載入中…</p>}
        {timeline.isError && <p className="py-16 text-center text-[hsl(var(--sell))]">載入失敗,請稍後再試。</p>}
        {timeline.data &&
          (filtered.length > 0 ? (
            <PostTimeline posts={filtered} />
          ) : (
            <p className="py-16 text-center text-muted-foreground">沒有符合篩選條件的貼文。</p>
          ))}
      </main>
    </div>
  );
}

function FilterChip({
  label,
  initial,
  avatarClass,
  count,
  icon,
  active,
  onClick,
}: {
  label: string;
  initial?: string;
  avatarClass?: string;
  count?: number;
  icon?: React.ReactNode;
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
            'flex size-5 items-center justify-center rounded-full text-[10px] font-semibold text-white',
            avatarClass ?? 'bg-primary text-primary-foreground',
          )}
        >
          {initial}
        </span>
      )}
      {icon}
      {label}
      {count !== undefined && (
        <span className={cn('font-mono text-xs', active ? 'text-primary-foreground/80' : 'text-muted-foreground')}>
          {count}
        </span>
      )}
    </button>
  );
}
