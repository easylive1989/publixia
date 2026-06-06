import { useState } from 'react';
import { Scorebar } from '@/components/Scorebar';
import { SectionHead } from '@/components/SectionHead';
import { LeaderboardCards } from '@/components/LeaderboardCards';
import { PlayByPlay } from '@/components/PlayByPlay';
import { useScoreboard, useTimeline } from '@/hooks/usePeople';

export default function TimelinePage() {
  const scoreboard = useScoreboard();
  const timeline = useTimeline(120);
  const [person, setPerson] = useState('all');
  const [signalOnly, setSignalOnly] = useState(false);

  const standings = scoreboard.data ?? [];
  const posts = timeline.data ?? [];
  const allKeys = standings.map((s) => s.person_key);

  return (
    <div>
      <Scorebar />
      <main className="wrap">
        <SectionHead zh="戰績排行榜" en="LEADERBOARD" note="點老師可篩選下方動態" />
        {scoreboard.isLoading ? (
          <div className="empty-note">載入中…</div>
        ) : (
          <LeaderboardCards standings={standings} allKeys={allKeys} person={person} onPerson={setPerson} />
        )}

        <SectionHead zh="喊單實況" en="TIMELINE" note="所有追蹤對象的最新動態（新→舊）" />
        <PlayByPlay
          posts={posts}
          standings={standings}
          allKeys={allKeys}
          person={person}
          setPerson={setPerson}
          signalOnly={signalOnly}
          setSignalOnly={setSignalOnly}
        />
      </main>
    </div>
  );
}
