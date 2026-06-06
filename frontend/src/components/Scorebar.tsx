import { NavLink } from 'react-router-dom';

const navClass = ({ isActive }: { isActive: boolean }) => 'nav-link' + (isActive ? ' on' : '');

export function Scorebar() {
  return (
    <header className="scorebar">
      <div className="scorebar-in">
        <NavLink to="/" className="wordmark">
          <span className="zh">對帳時刻</span>
          <span className="en">STOCK GURU SCOREBOARD</span>
        </NavLink>
        <nav className="scorebar-nav">
          <NavLink to="/" end className={navClass}>計分板</NavLink>
          <NavLink to="/timeline" className={navClass}>時間軸</NavLink>
          <span className="live-pill"><span className="live-dot" />本季 LIVE</span>
        </nav>
      </div>
    </header>
  );
}
