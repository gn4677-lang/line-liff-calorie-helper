import React from 'react';
import { Icon } from './Icon';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: keyof typeof import('../../lib/icons').ICONS;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className = '', icon, ...props }, ref) => {
    return (
      <div className={`input-wrapper ${className}`}>
        {icon && <Icon name={icon} className="text-[var(--icon-secondary)]" />}
        <input ref={ref} className="input-field" {...props} />
      </div>
    );
  }
);

Input.displayName = 'Input';
