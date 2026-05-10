import { Link } from 'react-router-dom';
import { useMe } from '@/hooks/useStrategy';

export function ForeignFuturesNavLink() {
  const { data: me } = useMe();
  if (!me?.can_view_foreign_futures) return null;
  return (
    <Link
      to="/futures/tw/foreign-flow"
      className="text-sm font-medium hover:underline text-muted-foreground"
    >
      外資期貨動向
    </Link>
  );
}
