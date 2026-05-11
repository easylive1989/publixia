import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ForeignFuturesResponse } from '@/hooks/useForeignFutures';
import {
  buildForeignFlowFilename,
  buildForeignFlowMarkdown,
} from '@/lib/foreign-flow-markdown';

interface DownloadFiveDaysButtonProps {
  data: ForeignFuturesResponse | undefined;
  disabled?: boolean;
}

function todayString(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function DownloadFiveDaysButton({
  data,
  disabled,
}: DownloadFiveDaysButtonProps) {
  const isDisabled = disabled || !data || data.dates.length === 0;

  function handleClick() {
    if (!data || data.dates.length === 0) return;
    const downloadDate = todayString();
    const md = buildForeignFlowMarkdown(data, downloadDate);
    const filename = buildForeignFlowFilename(downloadDate);
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      disabled={isDisabled}
      onClick={handleClick}
      aria-label="下載最近 5 個交易日資料供 AI 分析"
      className="gap-1"
    >
      <Download className="h-4 w-4" />
      下載 5 日資料
    </Button>
  );
}
