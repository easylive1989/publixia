import { NavLink } from 'react-router-dom';

const navClass = ({ isActive }: { isActive: boolean }) => 'nav-link' + (isActive ? ' on' : '');

export function Scorebar() {
  return (
    <header className="scorebar">
      <div className="scorebar-in">
        <NavLink to="/" className="wordmark">
          <span className="logo-badge" aria-hidden>
            <span>全</span>
            <span>賣</span>
          </span>
          <span className="wordmark-text">
            <span className="en">CALL FOR MONEY</span>
            <span className="zh">對帳中</span>
          </span>
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
