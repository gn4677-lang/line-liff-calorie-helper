// ── API Helper ──
// Centralized API call function and base URL.

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function api<T>(
  path: string,
  authHeaders: Record<string, string>,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
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
