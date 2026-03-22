import { useState } from 'react';
import './MealTimeline.css';
import { Icon } from '../../ui/Icon';
import type { IconName } from '../../../lib/icons';
import { InlineEditor } from './InlineEditor';

export interface Meal {
  id: string;
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  description: string;
  kcal: number;
  status: 'confirmed' | 'rough' | 'pending';
}

interface MealTimelineProps {
  meals: Meal[];
  onSave?: (id: string, updates: Omit<Meal, 'id' | 'status'>) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
}

const TYPE_TO_ICON: Record<string, IconName> = {
  breakfast: 'breakfast',
  lunch: 'lunch',
  dinner: 'dinner',
  snack: 'snack',
};

const TYPE_TO_LABEL: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '點心',
};

export function MealTimeline({ meals, onSave, onDelete }: MealTimelineProps) {
  const [editingId, setEditingId] = useState<string | null>(null);

  if (!meals || meals.length === 0) {
    return (
      <div className="empty-timeline p-4 text-center text-[var(--text-muted)] text-[var(--text-body)]">
        今天還沒有任何紀錄。
      </div>
    );
  }

  return (
    <div className="meal-timeline p-4">
      {meals.map((meal) => {
        if (editingId === meal.id) {
          return (
            <InlineEditor 
              key={meal.id} 
              meal={meal} 
              onSave={async (id, updates) => {
                await onSave?.(id, updates);
                setEditingId(null);
              }}
              onDelete={async (id) => {
                await onDelete?.(id);
                setEditingId(null);
              }}
              onCancel={() => setEditingId(null)}
            />
          );
        }

        return (
          <div 
            key={meal.id} 
            className="meal-row card card-elev-card mb-3 p-3 flex items-center justify-between"
            onClick={() => setEditingId(meal.id)}
            role="button"
            tabIndex={0}
          >
            <div className="flex items-center gap-3 flex-1 overflow-hidden">
              <div className="icon-wrapper text-[var(--icon-primary)]">
                <Icon name={TYPE_TO_ICON[meal.type] || 'check'} size="md" />
              </div>
              <div className="content flex-1 truncate">
                <div className="meal-type text-[var(--text-caption)] text-[var(--text-muted)]">
                  {TYPE_TO_LABEL[meal.type] || '其他'}
                </div>
                <div className="description text-[var(--text-body)] text-[var(--text-primary)] font-medium truncate">
                  {meal.description}
                </div>
              </div>
            </div>
            <div className="flex items-center">
              <div className="kcal text-[var(--text-body)] text-[var(--text-secondary)]">
                {meal.kcal} <span className="text-[var(--text-caption)]">kcal</span>
              </div>
              {meal.status === 'confirmed' && (
                <Icon name="check" size="sm" className="ml-2 text-[var(--status-complete)]" />
              )}
              {meal.status === 'rough' && (
                <Icon name="alertTriangle" size="sm" className="ml-2 text-[var(--status-rough)]" />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
