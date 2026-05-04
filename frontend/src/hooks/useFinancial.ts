import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export type FinancialStatement = 'income' | 'balance' | 'cashflow';

export interface FinancialAnnualSummary {
  current_4q: { eps: number | null; revenue: number | null };
  previous_4q: { eps: number | null; revenue: number | null };
  eps_yoy_pct: number | null;
  revenue_yoy_pct: number | null;
}

export type FinancialRow = Record<string, number | string | null>;

export interface FinancialResponse {
  ticker: string;
  statement: FinancialStatement;
  quarters: number;
  ok: boolean;
  rows: FinancialRow[];
  annual_summary: FinancialAnnualSummary | null;
}

export function useFinancial(statement: FinancialStatement, quarters = 12) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<FinancialResponse>({
    queryKey: ['stock-financial', code, statement, quarters],
    queryFn: () =>
      apiFetch<FinancialResponse>(
        `/api/stocks/${encodeURIComponent(code)}/financial?statement=${statement}&quarters=${quarters}`,
      ),
    enabled: !!code,
  });
}
