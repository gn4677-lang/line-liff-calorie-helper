import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { api } from './api'
import { server } from './test/server'

describe('api helper', () => {
  it('returns parsed json for successful requests', async () => {
    server.use(
      http.get('/api/ping', ({ request }) => {
        expect(request.headers.get('x-test-header')).toBe('hello')
        return HttpResponse.json({ ok: true, source: 'msw' })
      }),
    )

    const result = await api<{ ok: boolean; source: string }>(
      '/api/ping',
      { 'X-Test-Header': 'hello' },
    )

    expect(result).toEqual({ ok: true, source: 'msw' })
  })

  it('throws the response body for failed requests', async () => {
    server.use(
      http.post('/api/fail', () => new HttpResponse('bad request', { status: 400 })),
    )

    await expect(
      api('/api/fail', {}, { method: 'POST', body: JSON.stringify({ sample: true }) }),
    ).rejects.toThrow('bad request')
  })
})
