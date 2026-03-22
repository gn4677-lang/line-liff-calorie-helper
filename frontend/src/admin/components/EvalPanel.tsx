import type { ObservabilityDashboard } from '../adminTypes'

type Props = {
  evalPanels: ObservabilityDashboard['eval_panels']
}

function BreakdownTable({
  title,
  rows,
}: {
  title: string
  rows: Array<{ label: string; count: number; avg_latency_ms?: number }>
}) {
  return (
    <div className="card" style={{ marginBottom: 0 }}>
      <div className="admin-panel-header"><strong>{title}</strong></div>
      <table className="admin-panel-table">
        <thead>
          <tr>
            <th>Label</th>
            <th>Count</th>
            {'avg_latency_ms' in (rows[0] ?? {}) ? <th>Avg Latency</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <td>{row.label}</td>
              <td>{row.count}</td>
              {'avg_latency_ms' in row ? <td>{row.avg_latency_ms ?? 0} ms</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function EvalPanel({ evalPanels }: Props) {
  return (
    <section className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Eval</h2>
      </div>
      <div className="admin-grid-cards" style={{ marginTop: 16 }}>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Memory Packet Runs</span>
          <strong className="admin-stat-value">{evalPanels.packet_coverage_summary.memory_packet_present_runs}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Communication Profile Runs</span>
          <strong className="admin-stat-value">{evalPanels.packet_coverage_summary.communication_profile_present_runs}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Planning Copy Runs</span>
          <strong className="admin-stat-value">{evalPanels.packet_coverage_summary.planning_copy_attempted_runs}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-caption text-muted">Knowledge Packet Runs</span>
          <strong className="admin-stat-value">{evalPanels.packet_coverage_summary.knowledge_packet_version_runs}</strong>
        </article>
      </div>
      <div className="admin-grid-two" style={{ marginTop: 16 }}>
        <BreakdownTable title="Execution Phase" rows={evalPanels.execution_phase_breakdown} />
        <BreakdownTable title="Ingress Mode" rows={evalPanels.ingress_mode_breakdown} />
      </div>
      <div className="admin-grid-two" style={{ marginTop: 16 }}>
        <BreakdownTable title="Webhook Worker Status" rows={evalPanels.webhook_worker_status_breakdown} />
        <BreakdownTable title="Fallback Reasons" rows={evalPanels.fallback_reason_breakdown} />
      </div>
      <div className="admin-grid-two" style={{ marginTop: 16 }}>
        <BreakdownTable title="Unknown Labels" rows={evalPanels.top_unknown_labels} />
        <BreakdownTable title="Feedback Labels" rows={evalPanels.top_feedback_labels} />
      </div>
      <div className="card" style={{ marginTop: 16, marginBottom: 0 }}>
        <div className="admin-panel-header"><strong>Deterministic Integration Errors</strong></div>
        <table className="admin-panel-table">
          <thead>
            <tr>
              <th>Error Code</th>
              <th>Count</th>
            </tr>
          </thead>
          <tbody>
            {evalPanels.deterministic_integration_error_codes.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{row.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
