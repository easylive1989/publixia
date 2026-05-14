const API_BASE = import.meta.env.PROD
  ? 'https://api.paul-learning.dev'
  : '';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function _request(path: string, init: RequestInit): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const detail = await res.text();
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res;
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await _request(path, init);
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Variant of ``apiFetch`` that returns the raw text body. Used for
 *  endpoints that hand back markdown / plain text. */
export async function apiFetchText(
  path: string,
  init: RequestInit = {},
): Promise<string> {
  const res = await _request(path, init);
  return res.text();
}
