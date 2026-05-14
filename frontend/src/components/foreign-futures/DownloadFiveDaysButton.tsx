import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiFetchText, ApiError } from '@/lib/api-client';

interface DownloadFiveDaysButtonProps {
  disabled?: boolean;
}

function todayString(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function DownloadFiveDaysButton({ disabled }: DownloadFiveDaysButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setBusy(true);
    setError(null);
    try {
      const md = await apiFetchText(
        '/api/futures/tw/foreign-flow/markdown/download?time_range=1M',
      );
      const downloadDate = todayString();
      const filename = `foreign-flow_${downloadDate}.md`;
      const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `[${err.status}] ${err.message}`
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }

  const isDisabled = disabled || busy;

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={isDisabled}
        onClick={handleClick}
        aria-label="下載最近 5 個交易日資料供 AI 分析"
        className="gap-1"
      >
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Download className="h-4 w-4" />
        )}
        下載 5 日資料
      </Button>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
