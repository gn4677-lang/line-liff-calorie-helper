// ── API Helper ──
// Centralized API call function and base URL.

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function api<T>(
  path: string,
  authHeaders: Record<string, string>,
  init?: RequestInit,
): Promise<T> {
  const hasJsonBody = init?.body != null && !(init.body instanceof FormData)
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(hasJsonBody ? { 'Content-Type': 'application/json' } : {}),
      ...authHeaders,
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}
