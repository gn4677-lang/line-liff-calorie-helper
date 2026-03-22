import { Card } from '../../ui/Card';
import './CalorieHistory.css';

export interface TrendPoint {
  date: string;
  value: number;
  target?: number | null;
}

interface CalorieHistoryProps {
  points: TrendPoint[];
}

function formatShortDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' });
}

export function CalorieHistory({ points }: CalorieHistoryProps) {
  if (!points || !points.length) {
    return (
      <Card
        elevation="none"
        padding="md"
        className="mx-4 mb-4 border border-[var(--border-light)] border-dashed text-center"
      >
        <div className="text-[var(--text-small)] text-[var(--text-muted)]">No calorie history yet.</div>
      </Card>
    );
  }

  const max = Math.max(...points.map((point) => Math.max(Number(point.value), Number(point.target ?? 0), 1)));

  return (
    <Card elevation="card" padding="md" className="mx-4 mb-8 pb-6">
      <div className="mb-6 flex items-center justify-between">
        <h3 className="text-[var(--text-body)] font-medium text-[var(--text-primary)]">Calorie history</h3>
      </div>
      <div className="trend-bars">
        {points.slice(-7).map((point) => (
          <div key={point.date} className="trend-bars__item flex-1">
            <div className="trend-bars__track relative h-[120px] w-full overflow-hidden rounded-full bg-[var(--bg-page)]">
              {point.target != null && (
                <div
                  className="trend-bars__target absolute bottom-0 w-full bg-[var(--olive-light)] opacity-30"
                  style={{ height: `${Math.max(8, (Number(point.target) / max) * 100)}%` }}
                />
              )}
              <div
                className={`trend-bars__fill absolute bottom-0 w-full transition-all duration-500 ease-out ${Number(point.value) > Number(point.target ?? Infinity) ? 'bg-[var(--olive-medium)]' : 'bg-[var(--olive-deep)]'}`}
                style={{ height: `${Math.max(8, (Number(point.value) / max) * 100)}%` }}
              />
            </div>
            <span className="mt-2 text-[10px] font-medium tracking-tighter text-[var(--text-muted)]">
              {formatShortDate(point.date)}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
