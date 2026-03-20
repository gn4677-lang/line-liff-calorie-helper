import type { TraceDetailResponse } from '../adminTypes'

type Props = {
  detail: TraceDetailResponse | null
  onClose: () => void
}

function JsonBlock({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <section className="card admin-detail-block" style={{ marginBottom: 0 }}>
      <div className="admin-panel-header">
        <strong>{title}</strong>
        <span className="text-caption text-muted">{rows.length}</span>
      </div>
      {rows.length ? (
        rows.map((row, index) => <pre key={index}>{JSON.stringify(row, null, 2)}</pre>)
      ) : (
        <p className="text-caption text-muted">No events.</p>
      )}
    </section>
  )
}

export default function TraceDetailDrawer({ detail, onClose }: Props) {
  if (!detail) return null

  return (
    <aside className="admin-trace-drawer">
      <header className="admin-trace-drawer-header">
        <div>
          <h2 className="text-heading">Trace Detail</h2>
          <p className="text-caption text-muted">{String(detail.trace.id ?? '')}</p>
        </div>
        <button className="btn btn-outline" onClick={onClose}>Close</button>
      </header>
      <div className="admin-trace-drawer-body">
        <section className="card admin-detail-block" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header">
            <strong>Trace Header</strong>
          </div>
          <pre>{JSON.stringify(detail.trace, null, 2)}</pre>
        </section>
        <JsonBlock title="Execution Timeline" rows={detail.task_runs} />
        <JsonBlock title="Uncertainty / Confirmation" rows={detail.uncertainty_events} />
        <JsonBlock title="Knowledge / Grounding" rows={detail.knowledge_events} />
        <JsonBlock title="Operational Errors" rows={detail.error_events} />
        <JsonBlock title="User Feedback" rows={detail.feedback_events} />
        <JsonBlock title="Unknown Cases" rows={detail.unknown_case_events} />
        <JsonBlock title="Outcomes" rows={detail.outcome_events} />
        <JsonBlock title="Related Review Items" rows={detail.related_review_items as Array<Record<string, unknown>>} />
        <JsonBlock title="Related Alerts" rows={detail.related_alerts as Array<Record<string, unknown>>} />
      </div>
    </aside>
  )
}
