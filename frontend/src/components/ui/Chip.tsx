import React from 'react';

interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  label: string;
}

export function Chip({ active = false, label, className = '', ...props }: ChipProps) {
  const baseClasses = 'inline-flex items-center justify-center px-4 py-2 rounded-full text-[var(--text-body)] transition-all min-h-[36px] whitespace-nowrap active:scale-[0.97] disabled:opacity-50 border';
  
  const stateClasses = active
    ? 'bg-[var(--olive-soft)] border-[var(--olive-light)] text-[var(--olive-deep)]'
    : 'bg-transparent border-[var(--border-light)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]';

  return (
    <button
      type="button"
      className={`${baseClasses} ${stateClasses} ${className}`}
      {...props}
    >
      {label}
    </button>
  );
}
