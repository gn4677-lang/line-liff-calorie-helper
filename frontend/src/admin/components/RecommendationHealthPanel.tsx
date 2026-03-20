import type { ObservabilityDashboard } from '../adminTypes'

type Props = {
  product: ObservabilityDashboard['product_panels']
}

export default function RecommendationHealthPanel({ product }: Props) {
  const recommendation = product.recommendation_summary
  const body = product.body_goal_summary
  const proactive = product.proactive_summary
  const knowledge = product.knowledge_summary

  return (
    <section id="product-health" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Product Health</h2>
      </div>

      <div className="admin-grid-cards" style={{ marginBottom: 16 }}>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Eat Feed Sessions</span>
          <strong className="admin-stat-value">{recommendation.sessions}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Top Pick Accept Rate</span>
          <strong className="admin-stat-value">{recommendation.top_pick_accept_rate}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Correction Rate</span>
          <strong className="admin-stat-value">{recommendation.correction_rate}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Target Weight Coverage</span>
          <strong className="admin-stat-value">{body.target_weight_coverage}</strong>
        </article>
      </div>

      <div className="admin-grid-two">
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Recommendation Mix</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>Accepted Top Pick</td><td>{recommendation.accepted_top_pick}</td></tr>
              <tr><td>Accepted Backup Pick</td><td>{recommendation.accepted_backup_pick}</td></tr>
              <tr><td>Accepted Nearby</td><td>{recommendation.accepted_nearby}</td></tr>
              <tr><td>Corrected After Acceptance</td><td>{recommendation.corrected_after_acceptance}</td></tr>
              <tr><td>Backup Pick Accept Rate</td><td>{recommendation.backup_pick_accept_rate}</td></tr>
              <tr><td>Nearby Accept Rate</td><td>{recommendation.nearby_accept_rate}</td></tr>
            </tbody>
          </table>
        </div>

        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Body Model Coverage</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>Users with Body Goal</td><td>{body.body_goal_users}</td></tr>
              <tr><td>Users with Target Weight</td><td>{body.target_weight_users}</td></tr>
              <tr><td>Activity Adjustments</td><td>{body.activity_adjustment_events}</td></tr>
              <tr><td>Recommendation Profiles</td><td>{body.recommendation_profiles}</td></tr>
              <tr><td>Avg Profile Sample Size</td><td>{body.avg_profile_sample_size}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="admin-grid-two" style={{ marginTop: 16 }}>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Top Pick Source Breakdown</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {product.recommendation_source_breakdown.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Recommendation Session Status</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {product.recommendation_status_breakdown.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16, marginBottom: 0 }}>
        <div className="admin-panel-header"><strong>Proactive Push Summary</strong></div>
        <table className="admin-panel-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Daily Nudges</td><td>{proactive.daily_nudges}</td></tr>
            <tr><td>Meal Event Reminders</td><td>{proactive.meal_event_reminders}</td></tr>
            <tr><td>Dinner Picks</td><td>{proactive.dinner_picks}</td></tr>
            <tr><td>Meal Events Created</td><td>{proactive.meal_events_created}</td></tr>
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16, marginBottom: 0 }}>
        <div className="admin-panel-header"><strong>Knowledge Layer</strong></div>
        <table className="admin-panel-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Packet Version</td><td>{knowledge.version}</td></tr>
            <tr><td>Packs</td><td>{knowledge.pack_count}</td></tr>
            <tr><td>Docs</td><td>{knowledge.doc_count}</td></tr>
            <tr><td>Structured Items</td><td>{knowledge.structured_item_count}</td></tr>
            <tr><td>Pack IDs</td><td>{knowledge.pack_ids.join(', ') || '-'}</td></tr>
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16, marginBottom: 0 }}>
        <div className="admin-panel-header"><strong>Latest Recommendation Sessions</strong></div>
        <table className="admin-panel-table">
          <thead>
            <tr>
              <th>Created</th>
              <th>Top Pick</th>
              <th>Source</th>
              <th>Status</th>
              <th>Outcome</th>
            </tr>
          </thead>
          <tbody>
            {product.latest_recommendation_sessions.map((row) => (
              <tr key={row.id}>
                <td>{row.created_at}</td>
                <td>{row.top_pick_title || '-'}</td>
                <td>{row.top_pick_source || '-'}</td>
                <td>{row.status}</td>
                <td>{row.accepted_event_type || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
