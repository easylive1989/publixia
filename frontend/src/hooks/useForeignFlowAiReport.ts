import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api-client';

export interface ForeignFlowAiReport {
  report_date:     string;
  model:           string;
  prompt_version:  string;
  input_markdown:  string;
  output_markdown: string;
  generated_at:    string;
}

export const FOREIGN_FLOW_AI_REPORT_KEY = ['foreign-flow', 'ai-report', 'today'] as const;

/** Today's AI report from the backend.
 *
 *  404 surfaces as ``data === null`` (not as an error) so the empty
 *  state can render a "立即產生" button without spamming the console. */
export function useTodayForeignFlowAiReport(): UseQueryResult<ForeignFlowAiReport | null> {
  return useQuery<ForeignFlowAiReport | null>({
    queryKey: FOREIGN_FLOW_AI_REPORT_KEY,
    queryFn: async () => {
      try {
        return await apiFetch<ForeignFlowAiReport>(
          '/api/futures/tw/foreign-flow/ai-report/today',
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000,
  });
}

/** Manually trigger the Worker to (re)generate today's report.
 *
 *  Server-side this proxies a HTTP request to the Cloudflare Worker and
 *  blocks until the row lands in SQLite, so the response payload IS the
 *  fresh report. On success we invalidate the query cache anyway in case
 *  another tab is open. */
export function useRegenerateForeignFlowAiReport() {
  const qc = useQueryClient();
  return useMutation<ForeignFlowAiReport>({
    mutationFn: () =>
      apiFetch<ForeignFlowAiReport>(
        '/api/futures/tw/foreign-flow/ai-report/regenerate',
        { method: 'POST' },
      ),
    onSuccess: (report) => {
      qc.setQueryData(FOREIGN_FLOW_AI_REPORT_KEY, report);
    },
  });
}
