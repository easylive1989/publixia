import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useNews } from '@/hooks/useNews';
import { relativeTime } from '@/lib/relative-time';
import { registerCard } from './registry';

function NewsCard() {
  const { data, isLoading, isError } = useNews();
  return (
    <Card className="h-full sm:absolute sm:inset-0 flex flex-col">
      <CardHeader>
        <CardTitle>最新財經新聞</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto">
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {data && (
          <ul className="space-y-3">
            {data.map((item) => (
              <li key={item.url}>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm hover:underline"
                >
                  {item.title}
                </a>
                <p className="text-xs text-muted-foreground">
                  {item.source} · {relativeTime(item.published)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'news',
  label: '最新財經新聞',
  defaultPage: 'dashboard',
  component: NewsCard,
  cols: 1,
});
