import { Chip } from '../../ui/Chip';
import './ContextChooser.css';

interface ContextOption {
  id: string;
  label: string;
}

interface ContextChooserProps {
  options: ContextOption[];
  value: string | null;
  onChange: (id: string, label: string) => void;
  disabled?: boolean;
}

export function ContextChooser({ options, value, onChange, disabled }: ContextChooserProps) {
  return (
    <div className="context-chooser px-4 py-3 border-b border-[var(--border-subtle)]">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[var(--text-body)] font-medium text-[var(--text-secondary)]">Context</h3>
      </div>
      <div className="context-scroller">
        {options.map((option) => (
          <Chip
            key={option.id}
            label={option.label}
            active={value === option.id}
            disabled={disabled}
            onClick={() => onChange(option.id, option.label)}
            className="flex-shrink-0"
          />
        ))}
      </div>
    </div>
  );
}
