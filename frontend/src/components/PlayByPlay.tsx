import { Filters, FilterPerson } from '@/components/Filters';
import { Play } from '@/components/Play';
import { isCall } from '@/lib/verdict';
import type { Standing, TimelinePost } from '@/hooks/usePeople';

// Shared "喊單實況" section: person filter + signal-only toggle + the Play feed.
// Filter state is owned by the page so it's shared with the standings/leaderboard.
export function PlayByPlay({
  posts,
  standings,
  allKeys,
  person,
  setPerson,
  signalOnly,
  setSignalOnly,
}: {
  posts: TimelinePost[];
  standings: Standing[];
  allKeys: string[];
  person: string;
  setPerson: (p: string) => void;
  signalOnly: boolean;
  setSignalOnly: (v: boolean) => void;
}) {
  const filterPeople: FilterPerson[] = standings.map((s) => ({
    person_key: s.person_key,
    display_name: s.display_name,
    count: posts.filter((p) => p.person.person_key === s.person_key).length,
  }));

  const visible = posts.filter(
    (p) =>
      (person === 'all' || p.person.person_key === person) &&
      (!signalOnly || p.trades.some(isCall)),
  );

  return (
    <>
      <Filters
        people={filterPeople}
        allKeys={allKeys}
        person={person}
        onPerson={setPerson}
        signalOnly={signalOnly}
        onSignalOnly={setSignalOnly}
      />
      <div className="pbp">
        {visible.map((p) => (
          <Play key={p.id} post={p} allKeys={allKeys} />
        ))}
        {visible.length === 0 && <div className="empty-note">這個篩選條件下沒有貼文。</div>}
      </div>
    </>
  );
}
