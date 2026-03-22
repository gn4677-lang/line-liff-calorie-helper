import './StatusStrip.css';
import { Icon } from '../../ui/Icon';

interface StatusStripProps {
  currentDate: string;
  remainingKcal: number;
  consumedKcal: number;
  targetKcal: number;
  draftCount?: number;
  asyncCount?: number;
  onDateChange: (direction: 'prev' | 'next') => void;
}

export function StatusStrip({
  currentDate,
  remainingKcal,
  consumedKcal,
  targetKcal,
  draftCount = 0,
  asyncCount = 0,
  onDateChange,
}: StatusStripProps) {
  const dateObj = new Date(currentDate);
  const formattedDate = `${dateObj.getMonth() + 1}/${dateObj.getDate()}`;
  const today = new Date().toISOString().split('T')[0];
  const isToday = currentDate === today;

  return (
    <div className="status-strip border-b border-[var(--border-subtle)] px-4 py-3">
      <div className="status-header">
        <div className="date-nav text-[var(--text-body)] text-[var(--text-secondary)]">
          <button type="button" onClick={() => onDateChange('prev')} className="date-btn" aria-label="Previous Day">
            <Icon name="arrowLeft" size="sm" />
          </button>
          <span className="date-text font-medium">{isToday ? '今天' : formattedDate}</span>
          <button type="button" onClick={() => onDateChange('next')} disabled={isToday} className="date-btn" aria-label="Next Day">
            <Icon name="arrowRight" size="sm" />
          </button>
        </div>

        <div className="kcal-display">
          <div className="remaining text-[var(--text-hero)] font-bold leading-none text-[var(--olive-deep)]">{remainingKcal}</div>
          <div className="mt-1 text-right text-[var(--text-caption)] text-[var(--text-muted)]">
            {consumedKcal} / {targetKcal} kcal
          </div>
        </div>
      </div>

      {(draftCount > 0 || asyncCount > 0) && (
        <div className="badges mt-2">
          {draftCount > 0 && (
            <span className="badge">
              <Icon name="clock" size={12} className="mr-1" />
              {draftCount} 筆待確認
            </span>
          )}
          {asyncCount > 0 && (
            <span className="badge">
              <Icon name="loader" size={12} className="mr-1" />
              {asyncCount} 筆更新
            </span>
          )}
        </div>
      )}
    </div>
  );
}
