// A stable oklch hue per tracked person, used for jersey/avatar colors
// (`oklch(0.6 0.16 var(--hue))`). Assigned by the person's lexicographic rank
// in the full people list so colors stay stable even if the API reorders;
// falls back to a hash when the list isn't available yet.

const HUES = [158, 2, 283, 48, 220, 330, 95, 255];

export function personHue(personKey: string, allKeys?: string[]): number {
  if (allKeys && allKeys.length) {
    const i = [...allKeys].sort().indexOf(personKey);
    if (i >= 0) return HUES[i % HUES.length];
  }
  let h = 0;
  for (const ch of personKey) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return HUES[h % HUES.length];
}

export const initialOf = (displayName: string): string =>
  displayName ? [...displayName][0] : '?';
