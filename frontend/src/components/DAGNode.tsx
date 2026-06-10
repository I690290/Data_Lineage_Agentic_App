import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { LineageNode } from '@/types/lineage';
import { nodeColour, nodeLabel } from '@/utils/graphLayout';

interface LineageNodeData {
  lineageNode: LineageNode;
}

const LineageNodeComponent = memo(({ data, selected }: NodeProps<LineageNodeData>) => {
  const n = data.lineageNode;
  const colour = nodeColour(n.sub_type);
  const badge = nodeLabel(n.sub_type);
  const conf = n.confidence !== undefined ? Math.round(n.confidence * 100) : null;

  return (
    <div
      className={`
        relative flex flex-col rounded-lg border border-surface-border
        bg-surface-card shadow-lg transition-all
        ${selected ? 'ring-2 ring-primary-500' : ''}
      `}
      style={{ width: 200, minHeight: 80 }}
    >
      {/* Badge stripe */}
      <div className={`flex items-center gap-1.5 rounded-t-lg px-2 py-1 ${colour}`}>
        <span className="font-mono text-[10px] font-bold tracking-widest text-white">
          {badge}
        </span>
        <span className="truncate text-[11px] text-white/90">{n.system ?? n.language ?? ''}</span>
        {conf !== null && (
          <span className="ml-auto text-[10px] text-white/70">{conf}%</span>
        )}
      </div>

      {/* Name */}
      <div className="px-2 py-1.5">
        <p className="truncate font-mono text-xs font-semibold text-slate-200" title={n.name}>
          {n.name}
        </p>
        {n.description && (
          <p className="mt-0.5 truncate text-[10px] text-slate-400" title={n.description}>
            {n.description}
          </p>
        )}
      </div>

      <Handle type="target" position={Position.Left} className="!border-slate-600 !bg-slate-500" />
      <Handle type="source" position={Position.Right} className="!border-slate-600 !bg-slate-500" />
    </div>
  );
});

LineageNodeComponent.displayName = 'LineageNodeComponent';
export default LineageNodeComponent;
