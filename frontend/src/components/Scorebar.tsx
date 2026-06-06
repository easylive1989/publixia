import { NavLink } from 'react-router-dom';

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
        <span className="live-pill"><span className="live-dot" />本季 LIVE</span>
      </div>
    </header>
  );
}
