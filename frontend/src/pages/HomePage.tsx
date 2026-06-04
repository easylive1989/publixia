import { Masthead } from '@/components/Masthead';
import { PersonCard } from '@/components/PersonCard';
import { usePeople } from '@/hooks/usePeople';

export default function HomePage() {
  const { data: people, isLoading, isError } = usePeople();

  return (
    <div className="min-h-screen">
      <Masthead />
      <main className="container py-10">
        <div className="mb-8 max-w-2xl">
          <h1 className="font-display text-2xl font-semibold">追蹤名單</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            我們持續抓取這些人的貼文，用 AI 整理出他們買賣了哪些股票。點進去看每個人的動態與交易訊號。
          </p>
        </div>

        {isLoading && <p className="py-16 text-center text-muted-foreground">載入中…</p>}
        {isError && <p className="py-16 text-center text-[hsl(var(--sell))]">載入失敗，請稍後再試。</p>}

        {people && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {people.map((p, i) => (
              <PersonCard key={p.person_key} person={p} index={i} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
