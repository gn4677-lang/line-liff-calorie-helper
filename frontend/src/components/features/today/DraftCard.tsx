import { useState } from 'react';

import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { Icon } from '../../ui/Icon';
import type { Draft } from '../../../types';

interface DraftCardProps {
  draft: Draft;
  onConfirm: () => Promise<void>;
  onClarify: (answer: string) => Promise<void>;
}

export function DraftCard({ draft, onConfirm, onClarify }: DraftCardProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAction = async (action: () => Promise<void>) => {
    setLoading(true);
    setError(null);
    try {
      await action();
    } catch {
      setError('Unable to complete this action right now.');
    } finally {
      setLoading(false);
    }
  };

  const supportText =
    draft.followup_question ||
    draft.parsed_items.map((item) => item.name).join(' / ') ||
    draft.uncertainty_note ||
    'Review this draft before saving.';

  return (
    <Card padding="md" elevation="elevated" className="draft-card mx-4 my-4 border-[var(--olive-light)]">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--olive-soft)] text-[var(--olive-deep)]">
            <Icon name="clock" size="sm" />
          </div>
          <div>
            <div className="text-[var(--text-heading)] font-medium leading-tight text-[var(--text-primary)]">
              Pending meal draft
            </div>
            <div className="text-[var(--text-caption)] text-[var(--olive-deep)]">Estimate {draft.estimate_kcal} kcal</div>
          </div>
        </div>
        <span className="rounded-full bg-[var(--olive-muted)] px-2 py-1 text-[var(--text-small)] text-[var(--olive-medium)]">
          draft
        </span>
      </div>

      <p className="mb-4 text-[var(--text-body)] text-[var(--text-secondary)]">{supportText}</p>

      {error && (
        <div className="inline-error mb-4 flex items-center justify-between rounded-md border border-[var(--olive-light)] bg-[var(--olive-soft)] p-3 text-[var(--text-small)] text-[var(--olive-deep)]">
          <div className="flex items-center gap-2">
            <Icon name="alertTriangle" size="sm" />
            <span>{error}</span>
          </div>
          <button type="button" className="font-medium text-[var(--olive-deep)] underline" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {draft.followup_question ? (
        <div className="flex flex-wrap gap-2">
          {(draft.answer_options ?? []).map((option) => (
            <Button
              key={option}
              variant="outline"
              className="flex-1 whitespace-nowrap"
              isLoading={loading}
              onClick={() => handleAction(() => onClarify(option))}
            >
              {option}
            </Button>
          ))}
        </div>
      ) : (
        <div className="flex gap-3">
          <Button variant="primary" fullWidth isLoading={loading} loadingText="Saving..." onClick={() => handleAction(onConfirm)}>
            Confirm draft
          </Button>
        </div>
      )}
    </Card>
  );
}
