import type { TaskHealthRow } from '../adminTypes'

type Props = {
  rows: TaskHealthRow[]
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export default function TaskHealthTable({ rows }: Props) {
  const sorted = [...rows].sort((a, b) => (
    b.dissatisfaction_rate - a.dissatisfaction_rate ||
    b.fallback_rate - a.fallback_rate ||
    b.unknown_case_rate - a.unknown_case_rate
  ))

  return (
    <section id="task-health" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Task Health</h2>
      </div>
      <table className="admin-panel-table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Sample</th>
            <th>Success</th>
            <th>Fallback</th>
            <th>Unknown</th>
            <th>Dissatisfaction</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.task_family}>
              <td>{row.task_family}</td>
              <td>
                {row.sample_size}
                {row.sample_size < 5 ? <span className="badge badge-warning" style={{ marginLeft: 8 }}>Low sample</span> : null}
              </td>
              <td>{pct(row.success_rate)}</td>
              <td>{pct(row.fallback_rate)}</td>
              <td>{pct(row.unknown_case_rate)}</td>
              <td>{pct(row.dissatisfaction_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
