import type { TraceListItem } from '../adminTypes'

type Props = {
  traces: TraceListItem[]
  total: number
  offset: number
  limit: number
  onOffsetChange: (offset: number) => void
  onOpenTrace: (traceId: string) => void
}

export default function TraceListPanel({ traces, total, offset, limit, onOffsetChange, onOpenTrace }: Props) {
  const prevDisabled = offset <= 0
  const nextDisabled = offset + limit >= total

  return (
    <section id="trace-explorer" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Trace Explorer</h2>
        <span className="text-caption text-muted">{total} traces</span>
      </div>
      <table className="admin-panel-table">
        <thead>
          <tr>
            <th>Trace</th>
            <th>Task</th>
            <th>Surface</th>
            <th>Status</th>
            <th>Routing</th>
            <th>Latency</th>
            <th>Signals</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {traces.map((trace) => (
            <tr key={trace.trace_id} className="admin-click-row" onClick={() => onOpenTrace(trace.trace_id)}>
              <td>
                <div>{trace.trace_id.slice(0, 8)}</div>
                <div className="text-caption text-muted">{trace.created_at}</div>
              </td>
              <td>
                <div>{trace.task_family}</div>
                <div className="text-caption text-muted">{trace.input_preview}</div>
              </td>
              <td>{trace.surface}</td>
              <td>{trace.route_status}</td>
              <td>
                <div>{trace.execution_phase ?? 'n/a'} / {trace.ingress_mode ?? 'n/a'}</div>
                <div className="text-caption text-muted">
                  {(trace.route_policy ?? 'n/a')} / {(trace.route_target ?? 'n/a')}
                </div>
                <div className="text-caption text-muted">
                  {(trace.route_target ?? 'n/a')} / {(trace.provider_name ?? 'n/a')}
                </div>
                <div className="text-caption text-muted">
                  {(trace.model_name ?? 'n/a')} / cache {(trace.llm_cache ?? 'n/a')}
                </div>
              </td>
              <td>{trace.latency_ms ?? 'n/a'}</td>
              <td>
                <div className="admin-chip-row">
                  {trace.has_error ? <span className="badge badge-danger">error</span> : null}
                  {trace.has_feedback ? <span className="badge badge-warning">feedback</span> : null}
                  {trace.has_unknown_case ? <span className="badge badge-warning">unknown</span> : null}
                </div>
              </td>
              <td>{trace.outcome_summary}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="admin-pagination">
        <button className="btn btn-outline" disabled={prevDisabled} onClick={() => onOffsetChange(Math.max(offset - limit, 0))}>Prev</button>
        <span className="text-caption text-muted">{offset + 1}-{Math.min(offset + limit, total)} / {total}</span>
        <button className="btn btn-outline" disabled={nextDisabled} onClick={() => onOffsetChange(offset + limit)}>Next</button>
      </div>
    </section>
  )
}
