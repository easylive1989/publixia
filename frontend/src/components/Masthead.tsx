import { Link } from 'react-router-dom';

export function Masthead() {
  return (
    <header className="border-b-2 border-foreground">
      <div className="container flex items-end justify-between py-5">
        <Link to="/" className="group">
          <div className="font-display text-3xl font-bold leading-none tracking-tight sm:text-4xl">
            跟單<span className="italic">追蹤</span>
          </div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
            Copy-Trading Tracker
          </div>
        </Link>
        <div className="hidden text-right text-xs text-muted-foreground sm:block">
          追蹤社群名人的<br />一買一賣
        </div>
      </div>
    </header>
  );
}
