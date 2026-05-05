import { useMemo } from 'react';
import { useStockHistory } from '@/hooks/useStockHistory';
import { flattenHistory } from '@/lib/flatten-history';
import {
  KLineChart, VolumeChart, RSIChart, MACDChart,
} from '@/components/charts/PriceCharts';
import { registerCard } from './registry';

function KLineCard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  return <KLineChart rows={rows} />;
}

registerCard({
  id: 'stock-kline',
  label: 'K 線圖',
  defaultPage: 'stock',
  component: KLineCard,
  cols: 3,
});

function VolumeCard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  return <VolumeChart rows={rows} />;
}

registerCard({
  id: 'stock-volume',
  label: '成交量',
  defaultPage: 'stock',
  component: VolumeCard,
  cols: 3,
});

function RSICard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  return <RSIChart rows={rows} />;
}

registerCard({
  id: 'stock-rsi',
  label: 'RSI(14)',
  defaultPage: 'stock',
  component: RSICard,
  cols: 3,
});

function MACDCard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  return <MACDChart rows={rows} />;
}

registerCard({
  id: 'stock-macd',
  label: 'MACD(12,26,9)',
  defaultPage: 'stock',
  component: MACDCard,
  cols: 3,
});
