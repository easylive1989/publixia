import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface AlertRecord {
  id: number;
  target_type: 'indicator' | 'stock' | 'stock_indicator';
  target: string;
  indicator_key: string | null;
  condition: string;
  threshold: number;
  window_n: number | null;
  enabled: number | boolean;
  created_at: string;
  triggered_at: string | null;
  triggered_value: number | null;
}

export interface CreateAlertPayload {
  target_type: AlertRecord['target_type'];
  target: string;
  indicator_key?: string;
  condition: string;
  threshold: number;
  window_n?: number;
}

export function useAlerts() {
  return useQuery<AlertRecord[]>({
    queryKey: ['alerts'],
    queryFn: () => apiFetch<AlertRecord[]>('/api/alerts'),
  });
}

export function useCreateAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateAlertPayload) =>
      apiFetch('/api/alerts', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useDeleteAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api/alerts/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useToggleAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      apiFetch(`/api/alerts/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}
