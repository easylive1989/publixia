export function SectionHead({ zh, en, note }: { zh: string; en: string; note?: string }) {
  return (
    <div className="sec-head">
      <h2>{zh}</h2>
      <span className="en">{en}</span>
      {note && <span className="note">{note}</span>}
    </div>
  );
}
