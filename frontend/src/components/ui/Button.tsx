import React from 'react';
import { Icon } from './Icon';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline';
  isLoading?: boolean;
  loadingText?: string;
  icon?: keyof typeof import('../../lib/icons').ICONS;
  fullWidth?: boolean;
}

export function Button({
  children,
  variant = 'primary',
  isLoading = false,
  loadingText = '處理中...',
  icon,
  fullWidth = false,
  className = '',
  disabled,
  ...props
}: ButtonProps) {
  const baseClasses = 'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none min-h-[44px] px-4';
  
  const variants = {
    primary: 'bg-[var(--olive-deep)] text-[var(--text-on-primary)] hover:bg-[var(--olive-deep)]/90 border border-transparent',
    secondary: 'bg-[var(--olive-soft)] text-[var(--olive-deep)] hover:bg-[var(--olive-soft)]/90 border border-transparent',
    ghost: 'bg-transparent text-[var(--text-secondary)] hover:bg-[var(--olive-muted)] border border-transparent',
    outline: 'bg-transparent text-[var(--text-primary)] border border-[var(--border-light)] hover:bg-[var(--olive-muted)]',
  };

  const widthClass = fullWidth ? 'w-full flex-1' : '';

  return (
    <button
      className={`${baseClasses} ${variants[variant]} ${widthClass} ${className}`}
      disabled={isLoading || disabled}
      {...props}
    >
      {isLoading ? (
        <>
          <Icon name="loader" className="animate-spin" size="sm" />
          <span>{loadingText}</span>
        </>
      ) : (
        <>
          {icon && <Icon name={icon} size="sm" />}
          {children}
        </>
      )}
    </button>
  );
}
