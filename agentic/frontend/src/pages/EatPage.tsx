import type { AuthHeaders, HomePayload } from '../types'
import HomeScaffold from '../components/HomeScaffold'

type EatPageProps = {
  payload: HomePayload
  authHeaders: AuthHeaders
}

export default function EatPage({ payload }: EatPageProps) {
  return (
    <HomeScaffold payload={payload}>
      <article className="panel">
        <h2>Bounded Shortlist</h2>
        <div className="list-stack">
          {payload.state.recommendation_state.shortlist.map((item) => (
            <div className="list-card" key={item.key}>
              <div>
                <strong>{item.title}</strong>
                <p>{item.reason}</p>
              </div>
              <div className="badge-stack">
                <span>{item.kcal} kcal</span>
                {item.distance_m ? <span>{item.distance_m}m</span> : null}
              </div>
            </div>
          ))}
        </div>
      </article>
    </HomeScaffold>
  )
}
