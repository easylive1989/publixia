// Deterministic per-person colour so each tracked person reads consistently
// across the feed, filter chips and profile. Literal class strings so
// Tailwind's scanner keeps them.
//
// Assignment is by the person's lexicographic rank in the tracked-people list
// (not a hash of person_key) — with only a handful of people, a small palette,
// and short keys, hash-based slotting collided constantly. Sorting by
// person_key keeps the colour stable even as the API reorders people by latest
// activity. Falls back to a hash when the people list isn't loaded yet.
import { usePeople } from '@/hooks/usePeople';

export interface PersonColor {
  avatar: string; // background for the initial badge (white text on top)
  name: string; // name text colour (light/dark variants)
}

const PALETTE: PersonColor[] = [
  { avatar: 'bg-indigo-600', name: 'text-indigo-700 dark:text-indigo-400' },
  { avatar: 'bg-orange-600', name: 'text-orange-700 dark:text-orange-400' },
  { avatar: 'bg-teal-600', name: 'text-teal-700 dark:text-teal-400' },
  { avatar: 'bg-rose-600', name: 'text-rose-700 dark:text-rose-400' },
  { avatar: 'bg-violet-600', name: 'text-violet-700 dark:text-violet-400' },
  { avatar: 'bg-sky-600', name: 'text-sky-700 dark:text-sky-400' },
];

function hashSlot(key: string): number {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return h % PALETTE.length;
}

export function usePersonColor(key: string): PersonColor {
  const { data } = usePeople();
  if (data && data.length > 0) {
    const sorted = [...data].map((p) => p.person_key).sort();
    const idx = sorted.indexOf(key);
    if (idx >= 0) return PALETTE[idx % PALETTE.length];
  }
  return PALETTE[hashSlot(key)];
}
