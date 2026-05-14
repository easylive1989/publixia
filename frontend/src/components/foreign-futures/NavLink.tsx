import { Link } from 'react-router-dom';

export function ForeignFuturesNavLink() {
  return (
    <Link
      to="/futures/tw/foreign-flow"
      className="text-sm font-medium hover:underline text-muted-foreground"
    >
      外資期貨動向
    </Link>
  );
}
