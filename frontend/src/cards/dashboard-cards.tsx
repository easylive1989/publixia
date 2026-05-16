import type { FC } from 'react';
import { useDashboardData, type IndicatorSlot } from '@/hooks/useDashboardData';
import { useIndicatorHistory } from '@/hooks/useIndicatorHistory';
import { useRangeStore } from '@/store/range-store';
import { IndicatorCardView, type BadgeInfo } from '@/components/IndicatorCardView';
import { registerCard } from './registry';

type Extra = Record<string, unknown>;

interface IndicatorConfig {
  key: string;
  label: string;
  formatValue: (v: number, extra: Extra) => string;
  // Optional now — undefined means "no sub line, just rely on the
  // 'next update' annotation for temporal info". Cards that have
  // genuinely useful sub info (prev_close, contract, period…) keep
  // returning a string; pure "更新 YYYY-MM-DD" subs were removed since
  // the next-update annotation makes them redundant.
  formatSub?:  (extra: Extra) => string;
  formatBadge?: (extra: Extra, value: number) => BadgeInfo | null;
  valueClass?: (v: number, extra: Extra) => string | undefined;
  chartType?: 'line' | 'bar';
}

// Render a backend-supplied ISO timestamp (in TST, e.g. `2026-05-08T14:00:00+08:00`)
// as `MM-DD HH:MM` for display under each card. Returns '' on parse failure or
// when the value is missing.
function fmtNextUpdate(iso: string | null | undefined): string {
  if (!iso) return '';
  const m = iso.match(/^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return '';
  const [, mm, dd, hh, mi] = m;
  return `${mm}-${dd} ${hh}:${mi}`;
}

function asNumber(v: unknown): number | null {
  return typeof v === 'number' ? v : null;
}

function asString(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function changePctBadge(extra: Extra): BadgeInfo | null {
  const pct = asNumber(extra.change_pct);
  if (pct == null) return null;
  const tone: BadgeInfo['tone'] = pct >= 0 ? 'up' : 'down';
  const text = (pct >= 0 ? '▲ +' : '▼ ') + Math.abs(pct).toFixed(2) + '%';
  return { text, tone };
}

const CONFIGS: IndicatorConfig[] = [
  {
    key: 'taiex',
    label: '加權指數',
    formatValue: (v) => v.toLocaleString(),
    formatSub: (extra) => {
      const prev = asNumber(extra.prev_close);
      return `前收 ${prev != null ? prev.toLocaleString() : '—'}`;
    },
    formatBadge: (extra) => changePctBadge(extra),
  },
  {
    key: 'fx',
    label: '台幣兌美金',
    formatValue: (v) => v.toFixed(2),
    formatSub: (extra) => {
      const prev = asNumber(extra.prev_close);
      return `前收 ${prev != null ? prev.toFixed(2) : '—'}`;
    },
    formatBadge: (extra) => changePctBadge(extra),
  },
  {
    key: 'tw_volume',
    label: '台股成交金額',
    formatValue: (v) => v.toLocaleString() + ' 億',
    formatSub: (extra) => {
      const prev = asNumber(extra.prev_value);
      return `前日 ${prev != null ? prev.toLocaleString() : '—'} 億`;
    },
    formatBadge: (extra) => changePctBadge(extra),
    chartType: 'bar',
  },
  {
    key: 'fear_greed',
    label: '恐懼貪婪指數',
    formatValue: (v) => String(v),
    formatBadge: (extra) => {
      const label = asString(extra.label);
      return label ? { text: label, tone: 'neutral' } : null;
    },
    valueClass: (v) => (v < 45 ? 'text-red-600' : v > 55 ? 'text-green-600' : undefined),
  },
  {
    key: 'ndc',
    label: '國發會景氣指標',
    formatValue: (v) => `${v} 分`,
    formatSub: (extra) => `${asString(extra.period)} · 每月更新`,
    formatBadge: (extra) => {
      const light = asString(extra.light);
      return light ? { text: light, tone: 'neutral' } : null;
    },
  },
];

const EMPTY_EXTRA: Extra = {};

function makeCard(cfg: IndicatorConfig): FC {
  return function IndicatorCard() {
    const { data, isLoading, isError } = useDashboardData();
    const range = useRangeStore((s) => s.range);
    const history = useIndicatorHistory(cfg.key, range);
    const slot: IndicatorSlot | undefined = data?.[cfg.key];
    const error = isError
      ? '無法載入'
      : data && !slot
        ? '尚無資料'
        : undefined;
    const nextUpdate = slot ? fmtNextUpdate(slot.next_update_at) : '';
    return (
      <IndicatorCardView
        title={cfg.label}
        loading={isLoading}
        error={error}
        value={slot ? cfg.formatValue(slot.value, slot.extra) : undefined}
        valueClass={slot ? cfg.valueClass?.(slot.value, slot.extra) : undefined}
        sub={slot ? cfg.formatSub?.(slot.extra) : undefined}
        nextUpdate={nextUpdate || undefined}
        badge={slot ? cfg.formatBadge?.(slot.extra, slot.value) ?? null : null}
        series={history.data}
        formatSparkValue={(v) => cfg.formatValue(v, EMPTY_EXTRA)}
        chartType={cfg.chartType}
      />
    );
  };
}

CONFIGS.forEach((cfg) => {
  registerCard({
    id: cfg.key,
    label: cfg.label,
    defaultPage: 'dashboard',
    component: makeCard(cfg),
  });
});
