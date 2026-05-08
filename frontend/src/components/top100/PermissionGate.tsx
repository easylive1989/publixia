import { type ReactNode } from 'react';
import { useMe } from '@/hooks/useStrategy';

export function Top100PermissionGate({ children }: { children: ReactNode }) {
  const { data: me, isLoading } = useMe();
  if (isLoading) {
    return (
      <div className="container mx-auto p-8 text-muted-foreground">
        正在驗證權限…
      </div>
    );
  }
  if (!me?.can_view_top100) {
    return (
      <div className="container mx-auto p-8 max-w-xl">
        <h1 className="text-2xl font-bold mb-2">沒有台股百大權限</h1>
        <p className="text-muted-foreground">
          此功能僅開放給有權限的使用者。請聯繫 admin 開通。
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
