import React from 'react';

type BadgeVariant = 'default' | 'positive' | 'negative' | 'warning' | 'outline';

export function Badge({ 
  children, 
  variant = 'default',
  className = ''
}: { 
  children: React.ReactNode; 
  variant?: BadgeVariant;
  className?: string;
}) {
  
  const variants = {
    default: 'bg-surface-highlight text-text-main',
    positive: 'bg-positive/10 text-positive border border-positive/20',
    negative: 'bg-negative/10 text-negative border border-negative/20',
    warning: 'bg-warning/10 text-warning border border-warning/20',
    outline: 'border border-border text-text-muted',
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${variants[variant]} ${className}`}>
      {children}
    </span>
  );
}
