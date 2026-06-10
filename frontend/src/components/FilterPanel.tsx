import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

export type Language = 'COBOL' | 'Java' | 'SQL' | 'JCL' | 'all';
export type EntityType = 'File' | 'Table' | 'Column' | 'Program' | 'Job' | 'all';
export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'all';

export interface FilterState {
  language: Language;
  entityType: EntityType;
  confidence: ConfidenceLevel;
}

interface FilterPanelProps {
  filters: FilterState;
  onChange: (next: FilterState) => void;
}

const LANGUAGES: Language[] = ['all', 'COBOL', 'Java', 'SQL', 'JCL'];
const ENTITY_TYPES: EntityType[] = ['all', 'File', 'Table', 'Column', 'Program', 'Job'];
const CONFIDENCE_LEVELS: ConfidenceLevel[] = ['all', 'high', 'medium', 'low'];

/** FilterPanel — language, entity type, and confidence level filters for the DAG view. */
export default function FilterPanel({ filters, onChange }: FilterPanelProps) {
  const [open, setOpen] = React.useState(false);

  const set = <K extends keyof FilterState>(key: K, value: FilterState[K]) =>
    onChange({ ...filters, [key]: value });

  const activeCount = [
    filters.language !== 'all',
    filters.entityType !== 'all',
    filters.confidence !== 'all',
  ].filter(Boolean).length;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-lg border border-surface-border bg-surface px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-500"
      >
        Filters
        {activeCount > 0 && (
          <span className="rounded-full bg-primary-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
            {activeCount}
          </span>
        )}
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-52 rounded-lg border border-surface-border bg-surface-card p-3 shadow-lg">
          <FilterGroup
            label="Language"
            options={LANGUAGES}
            selected={filters.language}
            onSelect={(v) => set('language', v as Language)}
          />
          <FilterGroup
            label="Entity Type"
            options={ENTITY_TYPES}
            selected={filters.entityType}
            onSelect={(v) => set('entityType', v as EntityType)}
          />
          <FilterGroup
            label="Confidence"
            options={CONFIDENCE_LEVELS}
            selected={filters.confidence}
            onSelect={(v) => set('confidence', v as ConfidenceLevel)}
          />
          <button
            onClick={() => onChange({ language: 'all', entityType: 'all', confidence: 'all' })}
            className="mt-2 w-full rounded px-2 py-1 text-xs text-slate-400 hover:bg-surface hover:text-slate-200"
          >
            Reset all
          </button>
        </div>
      )}
    </div>
  );
}

function FilterGroup<T extends string>({
  label,
  options,
  selected,
  onSelect,
}: {
  label: string;
  options: T[];
  selected: T;
  onSelect: (v: T) => void;
}) {
  return (
    <div className="mb-2">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <div className="flex flex-wrap gap-1">
        {options.map((opt) => (
          <button
            key={opt}
            onClick={() => onSelect(opt)}
            className={`rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors ${
              selected === opt
                ? 'bg-primary-700 text-primary-200'
                : 'bg-surface text-slate-400 hover:text-slate-200'
            }`}
          >
            {opt === 'all' ? 'All' : opt}
          </button>
        ))}
      </div>
    </div>
  );
}
