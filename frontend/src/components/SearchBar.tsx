import React from 'react';
import { Search, X } from 'lucide-react';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

/** SearchBar — entity name search with clear button. */
export default function SearchBar({
  value,
  onChange,
  placeholder = 'Search entities…',
  className = '',
}: SearchBarProps) {
  return (
    <div
      className={`flex items-center gap-1.5 rounded-lg border border-surface-border bg-surface px-2.5 py-1.5 ${className}`}
    >
      <Search size={14} className="shrink-0 text-slate-500" />
      <input
        type="text"
        className="w-full bg-transparent text-xs text-slate-300 placeholder-slate-500 outline-none"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="shrink-0 text-slate-500 hover:text-slate-300"
          aria-label="Clear search"
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
}
