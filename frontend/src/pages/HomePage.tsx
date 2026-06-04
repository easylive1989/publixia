import { Link } from 'react-router-dom';
import { Masthead } from '@/components/Masthead';
import { PostTimeline } from '@/components/PostTimeline';
import { usePeople, useTimeline } from '@/hooks/usePeople';

export default function HomePage() {
  const people = usePeople();
  const timeline = useTimeline();

  return (
    <div className="min-h-screen">
      <Masthead />
      <main className="container max-w-3xl py-10">
        <div className="mb-6">
          <h1 className="font-display text-2xl font-semibold">動態時間軸</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            所有追蹤對象的貼文混合排序,AI 標出他們買賣了哪些股票。點作者可看個人完整動態。
          </p>
        </div>

        {/* 追蹤中的人物列(下鑽用) */}
        {people.data && people.data.length > 0 && (
          <div className="mb-8 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">追蹤中:</span>
            {people.data.map((p) => (
              <Link
                key={p.person_key}
                to={`/people/${p.person_key}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary px-3 py-1 text-sm hover:bg-accent"
              >
                <span className="flex size-5 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
                  {p.display_name.slice(0, 1)}
                </span>
                {p.display_name}
                <span className="font-mono text-xs text-muted-foreground">{p.trade_count}</span>
              </Link>
            ))}
          </div>
        )}

        {timeline.isLoading && <p className="py-16 text-center text-muted-foreground">載入中…</p>}
        {timeline.isError && <p className="py-16 text-center text-[hsl(var(--sell))]">載入失敗,請稍後再試。</p>}
        {timeline.data && <PostTimeline posts={timeline.data} />}
      </main>
    </div>
  );
}
