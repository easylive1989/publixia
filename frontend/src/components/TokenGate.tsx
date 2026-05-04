import { useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/store/auth-store';

export function TokenGate({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const setToken = useAuthStore((s) => s.setToken);
  const [input, setInput] = useState('');

  if (token) return <>{children}</>;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) setToken(input.trim());
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <form onSubmit={handleSubmit} className="w-full max-w-md p-6 space-y-4">
        <h1 className="text-2xl font-bold">Stock Dashboard</h1>
        <p className="text-sm text-muted-foreground">輸入 API token 以開始</p>
        <Input
          type="password"
          placeholder="sd_..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoFocus
        />
        <Button type="submit" className="w-full">登入</Button>
      </form>
    </div>
  );
}
