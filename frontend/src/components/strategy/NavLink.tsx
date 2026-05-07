import { Link } from 'react-router-dom';
import { useMe } from '@/hooks/useStrategy';

export function StrategiesNavLink() {
  const { data: me } = useMe();
  if (!me?.can_use_strategy) return null;
  return (
    <Link
      to="/strategies"
      className="text-sm font-medium hover:underline text-muted-foreground"
    >
      策略
    </Link>
  );
}
