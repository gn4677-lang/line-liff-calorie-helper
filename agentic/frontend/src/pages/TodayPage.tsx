import { useState } from 'react'

import { postTurn } from '../api'
import type { AgentTurnResult, AuthHeaders, HomePayload } from '../types'
import HomeScaffold from '../components/HomeScaffold'

type TodayPageProps = {
  payload: HomePayload
  authHeaders: AuthHeaders
}

export default function TodayPage({ payload, authHeaders }: TodayPageProps) {
  const [draft, setDraft] = useState('I overate yesterday. Help me choose a lighter dinner tonight.')
  const [result, setResult] = useState<AgentTurnResult | null>(null)
  const [status, setStatus] = useState<string>('')

  async function handleSend() {
    setStatus('thinking')
    try {
      const response = await postTurn(draft, authHeaders)
      setResult(response)
      setStatus('ready')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'request failed')
    }
  }

  return (
    <HomeScaffold payload={payload}>
      <div className="panel-grid">
        <article className="panel">
          <h2>Today Truth</h2>
          <p className="metric">{payload.state.today_state.remaining_kcal} kcal left</p>
          <p>{payload.state.today_state.open_drafts} open drafts</p>
          <p>{payload.state.today_state.pending_updates} pending updates</p>
        </article>

        <article className="panel">
          <h2>Agent Turn</h2>
          <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
          <button onClick={() => void handleSend()}>Send To Agent</button>
          {status ? <p className="status">{status}</p> : null}
          {result ? (
            <div className="response-box">
              <strong>{result.turn.understanding.primary_intent}</strong>
              <p>{result.turn.response.message_text}</p>
              {result.turn.response.followup_question ? <p>{result.turn.response.followup_question}</p> : null}
            </div>
          ) : null}
        </article>
      </div>
    </HomeScaffold>
  )
}
