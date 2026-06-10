import React from 'react';

interface ConfidenceBadgeProps {
  score: number; // 0.0 – 1.0
  showLabel?: boolean;
  size?: 'sm' | 'md';
}

/**
 * ConfidenceBadge — displays a colour-coded confidence indicator.
 * Green  ≥ 0.9  : AST-verified
 * Yellow 0.7–0.9 : partial verification
 * Red    < 0.7  : low confidence / needs review
 */
export default function ConfidenceBadge({
  score,
  showLabel = true,
  size = 'md',
}: ConfidenceBadgeProps) {
  const { bg, text, label } = getStyle(score);
  const px = size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center gap-1 rounded font-semibold ${px} ${bg} ${text}`}
      title={`Confidence: ${(score * 100).toFixed(0)}%`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
      {showLabel ? label : `${(score * 100).toFixed(0)}%`}
    </span>
  );
}

function getStyle(score: number): { bg: string; text: string; label: string } {
  if (score >= 0.9) return { bg: 'bg-emerald-900/70', text: 'text-emerald-300', label: 'High' };
  if (score >= 0.7) return { bg: 'bg-amber-900/70',   text: 'text-amber-300',   label: 'Med'  };
  return              { bg: 'bg-red-900/70',     text: 'text-red-300',     label: 'Low'  };
}
