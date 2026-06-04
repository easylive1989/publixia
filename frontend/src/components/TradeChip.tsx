import { cn } from '@/lib/utils';
import type { Direction, Trade } from '@/hooks/usePeople';

const DIRECTION_META: Record<
  Direction,
  { label: string; cls: string }
> = {
  buy: {
    label: '買進',
    cls: 'text-[hsl(var(--buy))] bg-[hsl(var(--buy)/0.10)] border-[hsl(var(--buy)/0.30)]',
  },
  sell: {
    label: '賣出',
    cls: 'text-[hsl(var(--sell))] bg-[hsl(var(--sell)/0.10)] border-[hsl(var(--sell)/0.30)]',
  },
  hold: {
    label: '續抱',
    cls: 'text-[hsl(var(--hold))] bg-[hsl(var(--hold)/0.12)] border-[hsl(var(--hold)/0.30)]',
  },
  bullish: {
    label: '看多',
    cls: 'text-[hsl(var(--buy))] bg-transparent border-[hsl(var(--buy)/0.40)] border-dashed',
  },
  bearish: {
    label: '看空',
    cls: 'text-[hsl(var(--sell))] bg-transparent border-[hsl(var(--sell)/0.40)] border-dashed',
  },
};

export function TradeChip({ trade }: { trade: Trade }) {
  const meta = DIRECTION_META[trade.direction];
  const symbol = trade.ticker ?? trade.raw_symbol;
  const lowConfidence = trade.confidence < 0.5;

  const extras: string[] = [];
  if (trade.price != null) extras.push(`@${trade.price}`);
  if (trade.quantity != null) extras.push(`${trade.quantity} 張`);

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-sm leading-none',
        meta.cls,
        lowConfidence && 'opacity-60',
      )}
      title={
        trade.ticker && trade.ticker !== trade.raw_symbol
          ? `原文：${trade.raw_symbol}　信心 ${(trade.confidence * 100).toFixed(0)}%`
          : `信心 ${(trade.confidence * 100).toFixed(0)}%`
      }
    >
      <span className="font-semibold">{meta.label}</span>
      <span className="font-mono font-medium tracking-tight">{symbol}</span>
      {trade.market && (
        <span className="text-[10px] font-mono uppercase opacity-60">{trade.market}</span>
      )}
      {extras.length > 0 && (
        <span className="font-mono text-xs opacity-80">{extras.join(' ')}</span>
      )}
    </span>
  );
}
