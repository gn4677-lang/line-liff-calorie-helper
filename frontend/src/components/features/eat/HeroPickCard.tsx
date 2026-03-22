import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { Icon } from '../../ui/Icon';
import './HeroPickCard.css';

interface HeroPickCardProps {
  item: {
    id: string;
    store_name: string;
    item_name: string;
    calorie_estimate: number;
    description: string;
    protein_grams?: number | null;
    hero_reason: string;
  };
  onAccept: (id: string) => Promise<void>;
  onReject: (id: string, reason: string) => Promise<void>;
  isLoading?: boolean;
}

export function HeroPickCard({ item, onAccept, onReject, isLoading }: HeroPickCardProps) {
  return (
    <Card elevation="float" padding="none" className="hero-pick-card mx-4 my-6 overflow-hidden">
      <div className="flex items-center gap-2 bg-[var(--olive-soft)] px-4 py-2">
        <Icon name="sparkles" size={14} className="text-[var(--olive-deep)]" />
        <span className="text-[var(--text-small)] font-medium text-[var(--olive-deep)]">
          {item.hero_reason || 'Recommended for you'}
        </span>
      </div>

      <div className="p-5">
        <div className="text-[var(--text-small)] tracking-wider text-[var(--text-muted)]">{item.store_name}</div>
        <h2 className="mt-1 mb-2 text-[var(--text-title)] font-bold leading-tight text-[var(--text-primary)]">
          {item.item_name}
        </h2>

        <p className="mb-6 line-clamp-2 text-[var(--text-body)] text-[var(--text-secondary)]">{item.description}</p>

        <div className="mb-6 flex gap-4">
          <div className="flex flex-col">
            <span className="text-[var(--text-heading)] font-bold leading-none text-[var(--olive-deep)]">
              {item.calorie_estimate}
            </span>
            <span className="mt-1 text-[var(--text-caption)] text-[var(--text-muted)]">kcal</span>
          </div>
          {item.protein_grams != null && (
            <div className="flex flex-col border-l border-[var(--border-subtle)] pl-4">
              <span className="mt-1 text-[var(--text-body)] font-medium leading-none text-[var(--text-primary)]">
                {item.protein_grams}g
              </span>
              <span className="mt-1 text-[var(--text-caption)] text-[var(--text-muted)]">protein</span>
            </div>
          )}
        </div>

        <div className="flex gap-3">
          <Button
            variant="outline"
            className="w-12 flex-shrink-0 !px-0 border-[var(--olive-light)] text-[var(--olive-medium)] hover:bg-[var(--olive-soft)]"
            disabled={isLoading}
            onClick={() => onReject(item.id, 'not-now')}
            aria-label="Reject recommendation"
          >
            <Icon name="xCircle" size="sm" />
          </Button>
          <Button
            variant="primary"
            fullWidth
            icon="check"
            isLoading={isLoading}
            onClick={() => onAccept(item.id)}
          >
            Take this pick
          </Button>
        </div>
      </div>
    </Card>
  );
}
