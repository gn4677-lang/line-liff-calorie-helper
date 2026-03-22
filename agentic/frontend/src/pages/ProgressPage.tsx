import type { AuthHeaders, HomePayload } from '../types'
import HomeScaffold from '../components/HomeScaffold'

type ProgressPageProps = {
  payload: HomePayload
  authHeaders: AuthHeaders
}

export default function ProgressPage({ payload }: ProgressPageProps) {
  return (
    <HomeScaffold payload={payload}>
      <div className="panel-grid">
        <article className="panel">
          <h2>Weekly Drift</h2>
          <p className="metric">{Math.round(payload.state.weekly_state.drift_pct * 100)}%</p>
          <p>Overlay: {payload.state.weekly_state.overlay_kcal} kcal</p>
        </article>

        <article className="panel">
          <h2>Future Events</h2>
          <ul>
            {payload.state.weekly_state.future_events.map((event) => (
              <li key={event.when}>
                {event.title} - {event.when}
              </li>
            ))}
          </ul>
        </article>
      </div>
    </HomeScaffold>
  )
}
