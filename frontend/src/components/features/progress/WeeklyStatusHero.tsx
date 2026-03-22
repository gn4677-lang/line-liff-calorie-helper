import { Card } from '../../ui/Card';
import { Icon } from '../../ui/Icon';

interface WeeklyStatusHeroProps {
  currentWeight: number | null;
  targetWeight: number | null;
  weeklyDeficit: number;
  tdee: number | null;
}

export function WeeklyStatusHero({
  currentWeight,
  targetWeight,
  weeklyDeficit,
  tdee,
}: WeeklyStatusHeroProps) {
  const isDeficit = weeklyDeficit > 0;

  return (
    <Card elevation="none" padding="lg" className="mx-4 my-4 bg-[var(--olive-soft)] border-none">
      <div className="flex flex-col gap-6">
        <div>
          <div className="text-[var(--text-caption)] text-[var(--olive-deep)] mb-1 flex items-center gap-1">
            <Icon name="target" size={14} />
            近期目標
          </div>
          <div className="flex items-end gap-3">
            <div className="flex items-baseline">
              <span className="text-[var(--text-hero)] font-bold text-[var(--olive-deep)] leading-none">
                {currentWeight ? currentWeight.toFixed(1) : '--'}
              </span>
              <span className="text-[var(--text-body)] font-medium text-[var(--olive-deep)] ml-1">
                kg
              </span>
            </div>
            {targetWeight && (
              <div className="text-[var(--text-body)] text-[var(--olive-medium)] pb-1">
                / {targetWeight.toFixed(1)} kg
              </div>
            )}
          </div>
        </div>

        {tdee && (
          <div className="flex flex-col">
            <div className="text-[var(--text-caption)] text-[var(--olive-deep)] mb-1 flex items-center gap-1">
              <Icon name="quick" size={14} />
              每日總消耗 (TDEE)
            </div>
            <div className="flex items-baseline">
              <span className="text-[var(--text-title)] font-bold leading-none text-[var(--olive-deep)]">
                {tdee}
              </span>
              <span className="text-[var(--text-small)] font-medium ml-1 text-[var(--olive-medium)]">
                kcal
              </span>
            </div>
          </div>
        )}

        <div className="flex flex-col">
          <div className="text-[var(--text-caption)] text-[var(--olive-deep)] mb-1 flex items-center gap-1">
            <Icon name="lineChart" size={14} />
            本週累積熱量餘額
          </div>
          <div className="flex items-baseline">
            <span className={`text-[var(--text-title)] font-bold leading-none ${isDeficit ? 'text-[var(--olive-deep)]' : 'text-[var(--text-primary)]'}`}>
              {isDeficit ? '-' : '+'}{Math.abs(weeklyDeficit)}
            </span>
            <span className={`text-[var(--text-small)] font-medium ml-1 ${isDeficit ? 'text-[var(--olive-medium)]' : 'text-[var(--text-secondary)]'}`}>
              kcal
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
}
