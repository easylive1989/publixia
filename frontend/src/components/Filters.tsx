import { initialOf, personHue } from '@/lib/person-hue';

export interface FilterPerson {
  person_key: string;
  display_name: string;
  count: number;
}

export function Filters({
  people,
  allKeys,
  person,
  onPerson,
  signalOnly,
  onSignalOnly,
}: {
  people: FilterPerson[];
  allKeys: string[];
  person: string;
  onPerson: (p: string) => void;
  signalOnly: boolean;
  onSignalOnly: (v: boolean) => void;
}) {
  return (
    <div className="filters">
      <button className={'tab' + (person === 'all' ? ' on' : '')} onClick={() => onPerson('all')}>
        全部
      </button>
      {people.map((p) => (
        <button
          key={p.person_key}
          className={'tab' + (person === p.person_key ? ' on' : '')}
          style={{ '--hue': personHue(p.person_key, allKeys) } as React.CSSProperties}
          onClick={() => onPerson(person === p.person_key ? 'all' : p.person_key)}
        >
          <span className="jd">{initialOf(p.display_name)}</span>
          {p.display_name}
          <span className="cnt">{p.count}</span>
        </button>
      ))}
      <button
        className={'tab toggle' + (signalOnly ? ' on' : '')}
        onClick={() => onSignalOnly(!signalOnly)}
      >
        只看喊單
      </button>
    </div>
  );
}
