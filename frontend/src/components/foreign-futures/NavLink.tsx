import { Link } from 'react-router-dom';

const linkClass = 'text-sm font-medium hover:underline text-muted-foreground';

export function ForeignFuturesNavLink() {
  return (
    <Link to="/futures/tw/foreign-flow" className={linkClass}>
      外資動向
    </Link>
  );
}

export function AiReportNavLink() {
  return (
    <Link to="/futures/tw/foreign-flow/ai-report" className={linkClass}>
      近日 AI 分析
    </Link>
  );
}
