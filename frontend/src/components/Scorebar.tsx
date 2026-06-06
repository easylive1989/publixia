import { NavLink } from 'react-router-dom';
import { nominateHref } from '@/lib/nominate';

export function Scorebar() {
  return (
    <header className="scorebar">
      <div className="scorebar-in">
        <NavLink to="/" className="wordmark">
          <span className="logo-mark" aria-hidden>全<br />員</span>
          <span className="wordmark-text">
            <span className="en">CALL FOR MONEY</span>
            <span className="zh">對帳中</span>
          </span>
        </NavLink>
        <div className="scorebar-right">
          <span className="live-pill"><span className="live-dot" />本季 LIVE</span>
          <a className="nominate-btn" href={nominateHref}>
            <span className="plus">＋</span>推薦參戰
          </a>
        </div>
      </div>
    </header>
  );
}
