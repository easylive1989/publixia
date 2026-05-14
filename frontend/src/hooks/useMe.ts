import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface MeResponse {
  user_id: number;
  name: string;
  can_view_foreign_futures: boolean;
}

export function useMe() {
  return useQuery<MeResponse>({
    queryKey: ['me'],
    queryFn: () => apiFetch<MeResponse>('/api/me'),
    staleTime: 60_000,
  });
}
