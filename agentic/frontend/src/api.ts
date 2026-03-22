import type {
  AgentTurnResult,
  AuthHeaders,
  ClientConfig,
  HomeKey,
  HomePayload,
  MeResponse,
  MutationResponse,
} from './types'

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, authHeaders: AuthHeaders = {}, init?: RequestInit): Promise<T> {
  const hasJsonBody = init?.body != null && !(init.body instanceof FormData)
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'same-origin',
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

export function getClientConfig(): Promise<ClientConfig> {
  return request<ClientConfig>('/api/client-config')
}

export function getMe(authHeaders: AuthHeaders = {}): Promise<MeResponse> {
  return request<MeResponse>('/api/me', authHeaders)
}

export function getHome(key: HomeKey, authHeaders: AuthHeaders = {}): Promise<HomePayload> {
  return request<HomePayload>(`/api/home/${key}`, authHeaders)
}

export function postTurn(text: string, authHeaders: AuthHeaders = {}): Promise<AgentTurnResult> {
  return request<AgentTurnResult>('/api/agent/turn', authHeaders, {
    method: 'POST',
    body: JSON.stringify({
      source: 'liff_turn',
      modalities: ['text'],
      text,
    }),
  })
}

export function updatePreferences(
  updates: Record<string, unknown>,
  authHeaders: AuthHeaders = {},
): Promise<MutationResponse> {
  return request<MutationResponse>('/api/settings/preferences', authHeaders, {
    method: 'POST',
    body: JSON.stringify({ updates, confirmed: true }),
  })
}

export function completeOnboarding(
  primaryGoal: string,
  constraints: string[],
  authHeaders: AuthHeaders = {},
): Promise<MutationResponse> {
  return request<MutationResponse>('/api/onboarding/complete', authHeaders, {
    method: 'POST',
    body: JSON.stringify({ primary_goal: primaryGoal, constraints, confirmed: true }),
  })
}
