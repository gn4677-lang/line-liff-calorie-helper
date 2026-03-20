import { API_BASE } from '../api'
import type { AdminApiResponse } from './adminTypes'

export const ADMIN_SESSION_KEY = 'observability_admin_session'

export function getStoredAdminToken(): string | null {
  return sessionStorage.getItem(ADMIN_SESSION_KEY)
}

export function setStoredAdminToken(token: string): void {
  sessionStorage.setItem(ADMIN_SESSION_KEY, token)
}

export function clearStoredAdminToken(): void {
  sessionStorage.removeItem(ADMIN_SESSION_KEY)
}

export async function adminApi<T>(path: string, token: string | null, init?: RequestInit): Promise<AdminApiResponse<T>> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(token ? { 'X-Admin-Session': token } : {}),
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`HTTP ${response.status}: ${text || 'Request failed'}`)
  }

  return response.json() as Promise<AdminApiResponse<T>>
}
