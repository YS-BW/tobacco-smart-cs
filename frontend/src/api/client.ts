const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ msg: res.statusText }));
    throw new Error(err.detail || err.msg || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  const json = await res.json();
  return json.data ?? json;
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export function isHttpError(error: unknown, status: number): boolean {
  return error instanceof Error && error.message.includes(`HTTP ${status}`);
}
