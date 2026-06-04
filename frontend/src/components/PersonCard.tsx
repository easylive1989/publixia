import { Link } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { relativeTime } from '@/lib/relative-time';
import { asUtc } from '@/lib/relative-time';
import type { PersonSummary } from '@/hooks/usePeople';

export function PersonCard({ person, index = 0 }: { person: PersonSummary; index?: number }) {
  const initial = person.display_name.slice(0, 1);
  const latest = person.latest_post_at ? relativeTime(asUtc(person.latest_post_at)) : '尚無貼文';

  return (
    <Link to={`/people/${person.person_key}`} className="group block animate-rise" style={{ animationDelay: `${index * 70}ms` }}>
      <Card className="relative h-full overflow-hidden p-6 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md">
        <ArrowUpRight className="absolute right-5 top-5 size-5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />

        <div className="flex items-center gap-4">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary font-display text-2xl font-semibold text-primary-foreground">
            {initial}
          </div>
          <div className="min-w-0">
            <h2 className="font-display text-2xl font-semibold leading-tight">{person.display_name}</h2>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {person.platforms.map((p) => (
                <span key={p} className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[11px] font-mono uppercase tracking-wide text-muted-foreground">
                  {p}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-6 flex items-end justify-between border-t border-dashed border-border pt-4">
          <div>
            <div className="font-ticker text-3xl font-semibold tabular-nums">{person.trade_count}</div>
            <div className="text-xs text-muted-foreground">累計交易訊號</div>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            最近發文<br />
            <span className="text-foreground">{latest}</span>
          </div>
        </div>
      </Card>
    </Link>
  );
}
