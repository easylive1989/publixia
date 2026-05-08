import { Link } from 'react-router-dom';
import { useMe } from '@/hooks/useStrategy';

export function Top100NavLink() {
  const { data: me } = useMe();
  if (!me?.can_view_top100) return null;
  return (
    <Link
      to="/tw-top100"
      className="text-sm font-medium hover:underline text-muted-foreground"
    >
      台股百大
    </Link>
  );
}
