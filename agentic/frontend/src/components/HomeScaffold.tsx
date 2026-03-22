import type { ReactNode } from 'react'

import type { HomePayload } from '../types'

type HomeScaffoldProps = {
  payload: HomePayload
  children?: ReactNode
}

export default function HomeScaffold({ payload, children }: HomeScaffoldProps) {
  return (
    <section className="home-shell">
      <header className="hero-card">
        <div className="eyebrow">{payload.persona.replaceAll('_', ' ')}</div>
        <h1>{payload.title}</h1>
        <p>{payload.state.conversation_state.rolling_summary}</p>
      </header>

      <div className="panel-grid">
        <article className="panel">
          <h2>Highlights</h2>
          <ul>
            {payload.highlights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>

        <article className="panel">
          <h2>Goal State</h2>
          <p className="metric">{payload.state.goal_state.primary_goal}</p>
          <p>{payload.state.goal_state.constraints.join(' / ')}</p>
          <p>{payload.state.goal_state.strategic_context.join(' / ')}</p>
        </article>

        <article className="panel">
          <h2>Delivery Preview</h2>
          {payload.delivery_preview ? (
            <>
              <p className="metric">{payload.delivery_preview.delivery_action}</p>
              <p>{payload.delivery_preview.why_now}</p>
            </>
          ) : (
            <p>No delivery preview.</p>
          )}
        </article>
      </div>

      {children}
    </section>
  )
}
