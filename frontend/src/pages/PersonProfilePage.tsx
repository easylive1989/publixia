import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { Masthead } from '@/components/Masthead';
import { PostTimeline } from '@/components/PostTimeline';
import { TradeChip } from '@/components/TradeChip';
import { usePersonProfile, usePersonPosts, type Trade } from '@/hooks/usePeople';

export default function PersonProfilePage() {
  const { personKey = '' } = useParams();
  const profile = usePersonProfile(personKey);
  const posts = usePersonPosts(personKey);

  const recentTrades = useMemo<Trade[]>(() => {
    const out: Trade[] = [];
    for (const post of posts.data ?? []) {
      for (const t of post.trades) {
        out.push(t);
        if (out.length >= 8) return out;
      }
    }
    return out;
  }, [posts.data]);

  return (
    <div className="min-h-screen">
      <Masthead />
      <main className="container py-8">
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> 返回追蹤名單
        </Link>

        {profile.isLoading && <p className="py-16 text-center text-muted-foreground">載入中…</p>}
        {profile.data === null && !profile.isLoading && (
          <p className="py-16 text-center text-muted-foreground">找不到這個追蹤對象。</p>
        )}

        {profile.data && (
          <>
            <div className="flex items-start gap-5 border-b-2 border-foreground pb-6">
              <div className="flex size-16 shrink-0 items-center justify-center rounded-full bg-primary font-display text-3xl font-semibold text-primary-foreground">
                {profile.data.display_name.slice(0, 1)}
              </div>
              <div className="min-w-0 flex-1">
                <h1 className="font-display text-4xl font-bold leading-none">{profile.data.display_name}</h1>
                <div className="mt-3 flex flex-wrap gap-3">
                  {profile.data.accounts.map((a) => (
                    <a
                      key={`${a.platform}-${a.handle}`}
                      href={a.profile_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary px-3 py-1 text-xs hover:bg-accent"
                    >
                      <span className="font-mono uppercase tracking-wide text-muted-foreground">{a.platform}</span>
                      <span>@{a.handle}</span>
                      <ExternalLink className="size-3 text-muted-foreground" />
                    </a>
                  ))}
                </div>
              </div>
            </div>

            {recentTrades.length > 0 && (
              <section className="mt-6">
                <h2 className="mb-3 font-display text-lg font-semibold">最新交易訊號</h2>
                <div className="flex flex-wrap gap-2">
                  {recentTrades.map((t, i) => (
                    <TradeChip key={`${t.raw_symbol}-${t.direction}-${i}`} trade={t} />
                  ))}
                </div>
              </section>
            )}

            <section className="mt-8">
              <h2 className="mb-5 font-display text-lg font-semibold">貼文動態</h2>
              {posts.isLoading && <p className="py-10 text-center text-muted-foreground">載入貼文中…</p>}
              {posts.isError && <p className="py-10 text-center text-[hsl(var(--sell))]">貼文載入失敗。</p>}
              {posts.data && <PostTimeline posts={posts.data} />}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
