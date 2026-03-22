import React from 'react';
import { ICONS, type IconName } from '../../lib/icons';

interface IconProps extends React.SVGProps<SVGSVGElement> {
  name: IconName;
  size?: 'sm' | 'md' | 'lg' | 'xl' | number;
  className?: string;
}

const sizeMap = {
  sm: 16,
  md: 20,
  lg: 24,
  xl: 32,
};

export function Icon({ name, size = 'md', className, ...props }: IconProps) {
  const LucideIcon = ICONS[name];
  
  if (!LucideIcon) {
    console.warn(`Icon "${name}" not found`);
    return null;
  }

  const numericSize = typeof size === 'string' ? sizeMap[size] : size;

  return (
    <LucideIcon
      width={numericSize}
      height={numericSize}
      strokeWidth={1.5}
      className={className}
      {...props}
    />
  );
}
