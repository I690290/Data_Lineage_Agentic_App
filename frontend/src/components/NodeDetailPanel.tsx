import React from 'react';
import type { LineageNode } from '@/types/lineage';
import { nodeColour } from '@/utils/graphLayout';
import { X, Database, FileCode, ArrowRightLeft, GitBranch } from 'lucide-react';

interface NodeDetailPanelProps {
  node: LineageNode;
  onClose: () => void;
}

const TYPE_ICONS: Record<string, React.ElementType> = {
  DataSource: Database,
  Dataset: Database,
  TransformationUnit: ArrowRightLeft,
  OracleView: GitBranch,
  OracleExternalTable: FileCode,
};

export default function NodeDetailPanel({ node, onClose }: NodeDetailPanelProps) {
  const Icon = TYPE_ICONS[node.type] ?? FileCode;
  const colour = nodeColour(node.sub_type);

  return (
    <div className="absolute right-4 top-4 z-10 w-80 rounded-xl border border-surface-border bg-surface-card shadow-2xl">
      {/* Header */}
      <div className={`flex items-center gap-2 rounded-t-xl px-4 py-3 ${colour}`}>
        <Icon size={16} className="shrink-0 text-white" />
        <h3 className="flex-1 truncate font-mono text-sm font-bold text-white" title={node.name}>
          {node.name}
        </h3>
        <button onClick={onClose} className="text-white/70 hover:text-white">
          <X size={16} />
        </button>
      </div>

      {/* Body */}
      <div className="space-y-3 p-4">
        {/* Meta */}
        <div className="space-y-1">
          <Row label="Type" value={node.type} />
          <Row label="Sub-Type" value={node.sub_type} />
          {node.system && <Row label="System" value={node.system} />}
          {node.language && <Row label="Language" value={node.language} />}
          {node.schema && <Row label="Schema" value={node.schema} />}
          {node.table && <Row label="Table" value={node.table} />}
          {node.confidence !== undefined && (
            <Row label="Confidence" value={`${Math.round(node.confidence * 100)}%`} />
          )}
        </div>

        {/* Description */}
        {node.description && (
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-widest text-slate-500">Description</p>
            <p className="text-xs text-slate-300">{node.description}</p>
          </div>
        )}

        {/* Columns */}
        {node.columns && node.columns.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-widest text-slate-500">
              Columns ({node.columns.length})
            </p>
            <ul className="max-h-40 space-y-0.5 overflow-y-auto">
              {node.columns.map((col) => (
                <li key={col} className="font-mono text-[11px] text-slate-300">
                  {col}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Copybooks */}
        {node.copybooks && node.copybooks.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-widest text-slate-500">Copybooks</p>
            <div className="flex flex-wrap gap-1">
              {node.copybooks.map((cb) => (
                <span
                  key={cb}
                  className="rounded bg-slate-700 px-1.5 py-0.5 font-mono text-[11px] text-slate-300"
                >
                  {cb}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-20 shrink-0 text-[10px] uppercase tracking-widest text-slate-500">
        {label}
      </span>
      <span className="font-mono text-xs text-slate-300">{value}</span>
    </div>
  );
}
