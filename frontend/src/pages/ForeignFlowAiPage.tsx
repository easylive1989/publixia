import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ForeignFlowAiReport } from '@/components/foreign-futures/ForeignFlowAiReport';

export default function ForeignFlowAiPage() {
  return (
    <div className="container mx-auto p-4 space-y-4">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1">
        <Link to="/" aria-label="返回 Dashboard">
          <ArrowLeft className="h-4 w-4" />
          返回 Dashboard
        </Link>
      </Button>
      <h1 className="text-2xl font-bold">近日 AI 分析</h1>
      <ForeignFlowAiReport />
    </div>
  );
}
