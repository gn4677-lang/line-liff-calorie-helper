import type { ReviewQueueItem } from '../adminTypes'

type Props = {
  items: ReviewQueueItem[]
  onStatus: (id: number, status: 'triaged' | 'in_progress' | 'resolved' | 'ignored') => void
  onOpenTrace: (traceId: string | null | undefined) => void
}

export default function ReviewQueuePanel({ items, onStatus, onOpenTrace }: Props) {
  return (
    <section id="review-queue" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Review Queue</h2>
      </div>
      {!items.length ? (
        <p className="text-caption text-muted">Review queue is clear.</p>
      ) : (
        <table className="admin-panel-table">
          <thead>
            <tr>
              <th>Priority</th>
              <th>Type</th>
              <th>Title</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.priority}</td>
                <td>{item.queue_type}</td>
                <td>
                  <div>{item.title}</div>
                  <div className="text-caption text-muted">{item.summary}</div>
                  {item.trace_id ? (
                    <button className="btn btn-outline" style={{ marginTop: 8 }} onClick={() => onOpenTrace(item.trace_id)}>
                      Open Trace
                    </button>
                  ) : null}
                </td>
                <td>{item.status}</td>
                <td>{item.created_at}</td>
                <td>
                  <div className="admin-actions-inline">
                    <button className="btn btn-outline" onClick={() => onStatus(item.id, 'triaged')}>Triaged</button>
                    <button className="btn btn-outline" onClick={() => onStatus(item.id, 'in_progress')}>In Progress</button>
                    <button className="btn btn-secondary" onClick={() => onStatus(item.id, 'resolved')}>Resolved</button>
                    <button className="btn btn-outline" onClick={() => onStatus(item.id, 'ignored')}>Ignored</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
