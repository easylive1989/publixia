import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  useFinancial, type FinancialResponse, type FinancialStatement,
} from '@/hooks/useFinancial';
import { registerCard } from './registry';

function fmtN(v: unknown, digits = 0): string {
  if (typeof v !== 'number') return '—';
  return v.toLocaleString(undefined, { maximumFractionDigits: digits });
}

interface RowSpec {
  key: string;
  label: string;
  digits?: number;
}

interface FinancialTableProps {
  data: FinancialResponse;
  rowSpecs: RowSpec[];
}

function FinancialTable({ data, rowSpecs }: FinancialTableProps) {
  const reversed = [...data.rows].reverse(); // newest first
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>項目</TableHead>
          {reversed.map((r) => (
            <TableHead key={String(r.date)} className="text-right">
              {String(r.date)}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rowSpecs.map((spec) => (
          <TableRow key={spec.key}>
            <TableCell className="font-medium">{spec.label}</TableCell>
            {reversed.map((r) => (
              <TableCell key={String(r.date)} className="text-right">
                {fmtN(r[spec.key], spec.digits ?? 0)}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

interface SummaryProps {
  summary: NonNullable<FinancialResponse['annual_summary']>;
}

function AnnualSummaryStrip({ summary }: SummaryProps) {
  function pct(v: number | null) {
    if (v == null) return <span>—</span>;
    const cls = v >= 0 ? 'text-green-600' : 'text-red-600';
    return <span className={cls}>{(v >= 0 ? '+' : '') + v.toFixed(2) + '%'}</span>;
  }
  return (
    <div className="grid grid-cols-2 gap-4 pb-3 mb-3 border-b text-sm">
      <div>
        <div className="text-xs text-muted-foreground">近 4 季 EPS</div>
        <div className="text-lg font-bold">
          {fmtN(summary.current_4q.eps, 2)}{' '}
          {pct(summary.eps_yoy_pct)}
        </div>
      </div>
      <div>
        <div className="text-xs text-muted-foreground">近 4 季營收</div>
        <div className="text-lg font-bold">
          {fmtN(summary.current_4q.revenue)}{' '}
          {pct(summary.revenue_yoy_pct)}
        </div>
      </div>
    </div>
  );
}

interface StatementCardProps {
  title: string;
  hint: string;
  statement: FinancialStatement;
  rowSpecs: RowSpec[];
  showAnnualSummary?: boolean;
}

function StatementCard({
  title, hint, statement, rowSpecs, showAnnualSummary,
}: StatementCardProps) {
  const { data } = useFinancial(statement);
  if (!data) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">{hint}</p>
      </CardHeader>
      <CardContent>
        {data.rows.length === 0 && (
          <p className="text-sm text-muted-foreground">尚無資料</p>
        )}
        {data.rows.length > 0 && (
          <>
            {showAnnualSummary && data.annual_summary && (
              <AnnualSummaryStrip summary={data.annual_summary} />
            )}
            <FinancialTable data={data} rowSpecs={rowSpecs} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

const INCOME_ROWS: RowSpec[] = [
  { key: 'revenue',              label: '營收' },
  { key: 'gross_profit',         label: '毛利' },
  { key: 'operating_income',     label: '營業利益' },
  { key: 'net_income',           label: '稅後淨利' },
  { key: 'eps',                  label: 'EPS', digits: 2 },
  { key: 'gross_margin_pct',     label: '毛利率 %', digits: 2 },
  { key: 'operating_margin_pct', label: '營益率 %', digits: 2 },
  { key: 'net_margin_pct',       label: '淨利率 %', digits: 2 },
];

function IncomeStatementCard() {
  return (
    <StatementCard
      title="損益表"
      hint="近 12 季"
      statement="income"
      rowSpecs={INCOME_ROWS}
      showAnnualSummary
    />
  );
}

registerCard({
  id: 'stock-income',
  label: '損益表',
  defaultPage: 'stock',
  component: IncomeStatementCard,
  cols: 3,
});

const BALANCE_ROWS: RowSpec[] = [
  { key: 'total_assets',          label: '總資產' },
  { key: 'current_assets',        label: '流動資產' },
  { key: 'cash',                  label: '現金' },
  { key: 'total_liabilities',     label: '總負債' },
  { key: 'current_liabilities',   label: '流動負債' },
  { key: 'long_term_liabilities', label: '長期負債' },
  { key: 'equity',                label: '股東權益' },
  { key: 'current_ratio',         label: '流動比率', digits: 2 },
  { key: 'debt_ratio_pct',        label: '負債比 %', digits: 2 },
  { key: 'equity_ratio_pct',      label: '權益比 %', digits: 2 },
];

function BalanceSheetCard() {
  return (
    <StatementCard
      title="資產負債表"
      hint="近 12 季"
      statement="balance"
      rowSpecs={BALANCE_ROWS}
    />
  );
}

registerCard({
  id: 'stock-balance',
  label: '資產負債表',
  defaultPage: 'stock',
  component: BalanceSheetCard,
  cols: 3,
});

const CASHFLOW_ROWS: RowSpec[] = [
  { key: 'operating_cf',   label: '營業 CF' },
  { key: 'investing_cf',   label: '投資 CF' },
  { key: 'financing_cf',   label: '融資 CF' },
  { key: 'free_cash_flow', label: '自由現金流' },
];

function CashFlowCard() {
  return (
    <StatementCard
      title="現金流量表"
      hint="近 12 季"
      statement="cashflow"
      rowSpecs={CASHFLOW_ROWS}
    />
  );
}

registerCard({
  id: 'stock-cashflow',
  label: '現金流量表',
  defaultPage: 'stock',
  component: CashFlowCard,
  cols: 3,
});
