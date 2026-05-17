import { Loader2, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api-client';
import {
  useLatestForeignFlowAiReport,
  useRegenerateForeignFlowAiReport,
} from '@/hooks/useForeignFlowAiReport';

export function ForeignFlowAiReport() {
  const latest = useLatestForeignFlowAiReport();
  const regenerate = useRegenerateForeignFlowAiReport();

  const hasReport = latest.data != null;
  const isWorking = latest.isLoading || regenerate.isPending;

  const generatedLabel = latest.data
    ? `分析日期 ${latest.data.report_date} · ${latest.data.model}`
    : null;

  function handleRegenerate() {
    regenerate.mutate();
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 p-4 sm:p-6">
        <div className="space-y-1">
          <CardTitle className="text-lg flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-amber-500" />
            AI 分析
          </CardTitle>
          {generatedLabel && (
            <p className="text-xs text-muted-foreground">{generatedLabel}</p>
          )}
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={isWorking}
          onClick={handleRegenerate}
          aria-label="重新產生今日 AI 分析"
          className="gap-1 shrink-0"
        >
          {regenerate.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          {regenerate.isPending ? '產生中…' : '產生今日'}
        </Button>
      </CardHeader>

      <CardContent className="p-4 pt-0 sm:p-6 sm:pt-0 space-y-3">
        {latest.isLoading && (
          <p className="text-sm text-muted-foreground">載入中…</p>
        )}

        {latest.isError && (
          <p className="text-sm text-destructive">
            無法載入 AI 分析: {(latest.error as Error).message}
          </p>
        )}

        {!latest.isLoading && !latest.isError && !hasReport && !regenerate.isPending && (
          <p className="text-sm text-muted-foreground">
            尚無 AI 分析。每日 18:30 自動產生,也可以按右上角「產生今日」現在產出。
          </p>
        )}

        {regenerate.isPending && (
          <p className="text-xs text-muted-foreground">
            正在請 Workers AI 分析,約需 10–30 秒。
          </p>
        )}

        {regenerate.isError && (
          <p className="text-sm text-destructive">
            產生失敗:{' '}
            {regenerate.error instanceof ApiError
              ? `[${regenerate.error.status}] ${regenerate.error.message}`
              : regenerate.error.message}
          </p>
        )}

        {hasReport && (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {latest.data!.output_markdown}
            </ReactMarkdown>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
