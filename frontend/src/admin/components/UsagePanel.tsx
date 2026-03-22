import type { ObservabilityDashboard } from '../adminTypes'

type Props = {
  usage: ObservabilityDashboard['usage_panels']
}

export default function UsagePanel({ usage }: Props) {
  return (
    <section id="usage" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Usage</h2>
      </div>
      {!usage.token_usage_available ? <div className="admin-note">{usage.note}</div> : null}
      <div className="admin-grid-cards" style={{ marginTop: 16 }}>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Saved Local Requests</span>
          <strong className="admin-stat-value">{usage.llm_path_summary.saved_local_requests}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Remote LLM Requests</span>
          <strong className="admin-stat-value">{usage.llm_path_summary.remote_llm_requests}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">LLM Cache Hits</span>
          <strong className="admin-stat-value">{usage.llm_path_summary.cache_hits}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Webhook Ingress Events</span>
          <strong className="admin-stat-value">{usage.llm_path_summary.webhook_ingress_events}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Webhook Worker Runs</span>
          <strong className="admin-stat-value">{usage.llm_path_summary.webhook_worker_runs}</strong>
        </article>
      </div>
      <div className="admin-grid-cards" style={{ marginTop: 16 }}>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Memory Packet Runs</span>
          <strong className="admin-stat-value">{usage.packet_coverage_summary.memory_packet_present_runs}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Communication Profile Runs</span>
          <strong className="admin-stat-value">{usage.packet_coverage_summary.communication_profile_present_runs}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Planning Copy Runs</span>
          <strong className="admin-stat-value">{usage.packet_coverage_summary.planning_copy_attempted_runs}</strong>
        </article>
      </div>
      <div className="admin-grid-two" style={{ marginTop: 16 }}>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Provider Requests</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Requests</th>
              </tr>
            </thead>
            <tbody>
              {usage.provider_request_counts.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Model Breakdown</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Model</th>
                <th>Requests</th>
                <th>Avg Latency</th>
              </tr>
            </thead>
            <tbody>
              {usage.model_request_breakdown.map((row) => (
                <tr key={`${row.provider_name}-${row.model_name}`}>
                  <td>{row.provider_name}</td>
                  <td>{row.model_name}</td>
                  <td>{row.request_count}</td>
                  <td>{row.avg_latency_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="admin-grid-two" style={{ marginTop: 16 }}>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Execution Phase Breakdown</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Phase</th>
                <th>Requests</th>
                <th>Avg Latency</th>
              </tr>
            </thead>
            <tbody>
              {usage.execution_phase_breakdown.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                  <td>{row.avg_latency_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Ingress Mode Breakdown</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Ingress</th>
                <th>Requests</th>
                <th>Avg Latency</th>
              </tr>
            </thead>
            <tbody>
              {usage.ingress_mode_breakdown.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                  <td>{row.avg_latency_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="admin-grid-two" style={{ marginTop: 16 }}>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Route Policy Breakdown</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Policy</th>
                <th>Requests</th>
                <th>Avg Latency</th>
              </tr>
            </thead>
            <tbody>
              {usage.route_policy_breakdown.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                  <td>{row.avg_latency_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Route Target Breakdown</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Target</th>
                <th>Requests</th>
                <th>Avg Latency</th>
              </tr>
            </thead>
            <tbody>
              {usage.route_target_breakdown.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                  <td>{row.avg_latency_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card" style={{ marginTop: 16, marginBottom: 0 }}>
        <div className="admin-panel-header"><strong>Planning Copy Breakdown</strong></div>
        <table className="admin-panel-table">
          <thead>
            <tr>
              <th>Copy Layer</th>
              <th>Requests</th>
              <th>Avg Latency</th>
            </tr>
          </thead>
          <tbody>
            {usage.planning_copy_breakdown.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{row.count}</td>
                <td>{row.avg_latency_ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card" style={{ marginTop: 16, marginBottom: 0 }}>
        <div className="admin-panel-header"><strong>LLM Cache Breakdown</strong></div>
        <table className="admin-panel-table">
          <thead>
            <tr>
              <th>Cache State</th>
              <th>Requests</th>
              <th>Avg Latency</th>
            </tr>
          </thead>
          <tbody>
            {usage.llm_cache_breakdown.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{row.count}</td>
                <td>{row.avg_latency_ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
