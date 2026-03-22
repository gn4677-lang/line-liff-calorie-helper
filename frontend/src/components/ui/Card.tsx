import React from 'react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padding?: 'none' | 'sm' | 'md' | 'lg';
  elevation?: 'none' | 'card' | 'elevated' | 'float';
}

export function Card({ padding = 'md', elevation = 'card', className = '', children, ...props }: CardProps) {
  const paddings = {
    none: 'p-0',
    sm: 'p-[var(--space-3)]',
    md: 'p-[var(--card-padding)]',
    lg: 'p-[var(--space-5)]',
  };

  const elevations = {
    none: 'shadow-[var(--shadow-none)]',
    card: 'shadow-[var(--shadow-card)] border border-[var(--border-subtle)]',
    elevated: 'shadow-[var(--shadow-elevated)] border border-[var(--border-light)]',
    float: 'shadow-[var(--shadow-float)] border border-[var(--border-light)]',
  };

  return (
    <div
      className={`bg-[var(--bg-card)] rounded-[var(--radius-lg)] ${paddings[padding]} ${elevations[elevation]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
