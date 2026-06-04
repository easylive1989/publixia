/** Backend posted_at is a naive-UTC ISO string (no zone). Append 'Z' so the
 *  browser parses it as UTC rather than local time. */
export function asUtc(iso: string): string {
  if (!iso) return iso;
  return /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const diffMin = Math.round((now.getTime() - t) / 60_000);
  if (diffMin < 1) return '剛剛';
  if (diffMin < 60) return `${diffMin} 分鐘前`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小時前`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 7) return `${diffDay} 天前`;
  return iso.slice(0, 10);
}
