// Deterministic per-person colour so each tracked person reads consistently
// across the feed, filter chips and profile. Keyed by person_key (stable as
// people are added). Literal class strings so Tailwind's scanner keeps them.
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

export function personColor(key: string): PersonColor {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
