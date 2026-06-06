import { useState } from 'react';
import { Scorebar } from '@/components/Scorebar';
import { SectionHead } from '@/components/SectionHead';
import { Standings } from '@/components/Standings';
import { PlayByPlay } from '@/components/PlayByPlay';
import { Footer } from '@/components/Footer';
import { nominateHref } from '@/lib/nominate';
import { useScoreboard, useTimeline } from '@/hooks/usePeople';

export default function ScoreboardPage() {
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
        <SectionHead zh="戰績排行榜" en="STANDINGS" note="依累積跟單損益排名 · 點名字可篩選下方喊單" />
        {scoreboard.isLoading ? (
          <div className="empty-note">載入中…</div>
        ) : standings.length === 0 ? (
          <div className="empty-note">尚無資料</div>
        ) : (
          <Standings standings={standings} allKeys={allKeys} person={person} onPerson={setPerson} />
        )}

        <SectionHead zh="喊單實況" en="PLAY-BY-PLAY" note="每則貼文逐筆判定，AI 標記喊了哪些股票" />
        <PlayByPlay
          posts={posts}
          standings={standings}
          allKeys={allKeys}
          person={person}
          setPerson={setPerson}
          signalOnly={signalOnly}
          setSignalOnly={setSignalOnly}
        />

        <div className="roster-cta">
          <div className="rc-text">
            <span className="rc-kicker">MISSING SOMEONE?</span>
            <p>覺得誰的喊單該被攤開對帳？提名他，編審台會開始追蹤。</p>
          </div>
          <a className="nominate-btn lg" href={nominateHref} target="_blank" rel="noopener noreferrer">
            <span className="plus">＋</span>推薦老師參戰
          </a>
        </div>
      </main>

      <Footer />
    </div>
  );
}
