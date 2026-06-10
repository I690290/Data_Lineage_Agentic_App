import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import { useQuery } from '@tanstack/react-query';
import { X, Code2, Table2, ChevronRight, Database, FileCode, GitBranch } from 'lucide-react';
import { lineageApi } from '@/api/client';
import type { ColumnFlowEdge, ColumnFlowEntity } from '@/types/lineage';

// ─── colour palette ────────────────────────────────────────────────────────
const ENTITY_COLOR: Record<string, string> = {
  DB2Table:            '#6d28d9',   // violet
  OracleTable:         '#b45309',   // amber-700 (Oracle)
  OracleExternalTable: '#d97706',   // amber-600
  OracleView:          '#7c3aed',   // violet-600
  MainframeDataset:    '#0369a1',   // sky-700
  XMLFile:             '#c2410c',   // orange-700
  COBOLProgram:        '#1d4ed8',   // blue-700
  JCLUtility:          '#3730a3',   // indigo-700
  SQLScript:           '#b45309',   // amber (Oracle SQL script)
  default:             '#374151',
};

const SYSTEM_ICON: Record<string, React.ReactNode> = {
  DB2:     <Database size={10} />,
  Oracle:  <Database size={10} />,
  'z/OS':  <FileCode size={10} />,
  VSAM:    <FileCode size={10} />,
  COBOL:   <Code2 size={10} />,
  JCL:     <GitBranch size={10} />,
};

// ─── custom node: entity card ───────────────────────────────────────────────
function EntityNode({ data }: NodeProps) {
  const bg = ENTITY_COLOR[data.sub_type] ?? ENTITY_COLOR.default;
  const cols: string[] = data.columns ?? [];
  return (
    <div
      style={{ borderColor: bg, minWidth: 185, maxWidth: 230 }}
      className="rounded-xl border-2 bg-surface-card shadow-lg overflow-hidden text-[11px]"
    >
      <div style={{ backgroundColor: bg }} className="flex items-center gap-1.5 px-3 py-1.5 text-white font-semibold">
        {SYSTEM_ICON[data.system] ?? <Database size={10} />}
        <span className="truncate" title={data.label}>{data.label}</span>
        <span className="ml-auto shrink-0 rounded bg-white/20 px-1 text-[9px] font-mono">{data.system}</span>
      </div>
      <div className="max-h-52 overflow-y-auto divide-y divide-surface-border">
        {cols.length === 0 ? (
          <p className="px-3 py-2 text-slate-500 italic">no columns captured</p>
        ) : (
          cols.map((col) => (
            <div key={col} className="flex items-center gap-1.5 px-3 py-[3px] text-slate-300 hover:bg-surface">
              <span className="h-1.5 w-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: bg }} />
              <span className="truncate font-mono text-[10px]" title={col}>{col}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ─── custom node: program/transform step ───────────────────────────────────
function ProgramNode({ data, selected }: NodeProps) {
  const sub_type: string = data.sub_type ?? 'COBOLProgram';
  const bg = ENTITY_COLOR[sub_type] ?? ENTITY_COLOR.default;
  const langBadge: Record<string, string> = { cobol: 'CBL', jcl: 'JCL', sql: 'SQL' };
  const badge = langBadge[data.language] ?? 'PRG';
  // For COBOL: show paragraph name on top, program name below
  // For SQL: show script name + SQL badge
  const mainLabel = data.transform_name || data.label;
  const subLabel  = data.language !== 'sql' && data.program_name !== mainLabel
    ? data.program_name
    : '';
  return (
    <div
      style={{ borderColor: selected ? '#38bdf8' : bg, minWidth: 170 }}
      className="rounded-xl border-2 bg-surface-card shadow-lg cursor-pointer transition-all"
      title="Click to view column mappings and code snippet"
    >
      <div style={{ backgroundColor: bg }}
        className="flex items-center gap-1.5 px-3 py-1.5 text-white text-[11px] font-semibold rounded-t-[9px]"
      >
        <Code2 size={10} />
        <span className="truncate max-w-[140px]" title={mainLabel}>{mainLabel}</span>
        <span className="ml-auto rounded bg-white/20 px-1 text-[9px] font-bold">{badge}</span>
      </div>
      <div className="px-3 py-1.5 space-y-0.5">
        {subLabel && (
          <p className="text-[10px] text-slate-400 font-mono truncate" title={subLabel}>
            in {subLabel}
          </p>
        )}
        {data.transform_type && (
          <span className="inline-block rounded bg-surface px-1 py-0.5 font-mono text-[9px] text-slate-300">
            {data.transform_type}
          </span>
        )}
        {data.confidence_score != null && (
          <span className="ml-1.5 text-[10px] text-slate-500">
            {Math.round((data.confidence_score as number) * 100)}% conf
          </span>
        )}
      </div>
    </div>
  );
}

const NODE_TYPES = { entityNode: EntityNode, programNode: ProgramNode };

// ─── dagre layout ───────────────────────────────────────────────────────────
const ENTITY_W = 200;
const ENTITY_H = 200; // approximate, varies with column count
const PROGRAM_W = 180;
const PROGRAM_H = 60;

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 80 });
  nodes.forEach((n) => {
    const w = n.type === 'programNode' ? PROGRAM_W : ENTITY_W;
    const h = n.type === 'programNode' ? PROGRAM_H : ENTITY_H;
    g.setNode(n.id, { width: w, height: h });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    const w = n.type === 'programNode' ? PROGRAM_W : ENTITY_W;
    const h = n.type === 'programNode' ? PROGRAM_H : ENTITY_H;
    return { ...n, position: { x: pos.x - w / 2, y: pos.y - h / 2 } };
  });
}

// ─── build react-flow nodes + edges from ColumnFlowGraph ───────────────────
function buildFlowGraph(
  entities: ColumnFlowEntity[],
  flows: ColumnFlowEdge[],
): { rfNodes: Node[]; rfEdges: Edge[] } {
  const rfNodes: Node[] = [];
  const rfEdges: Edge[] = [];

  // Entity nodes
  const entityIdMap: Record<string, string> = {};
  entities.forEach((e) => {
    entityIdMap[e.name] = e.id;
    rfNodes.push({
      id: e.id,
      type: 'entityNode',
      position: { x: 0, y: 0 },
      data: {
        label: e.name,
        sub_type: e.type,
        system: e.system,
        columns: e.columns,
      },
    });
  });

  // For each flow: add a program node + two edges (entity→program→entity)
  const seenPrograms = new Map<string, string>(); // stepId → rfNodeId
  flows.forEach((flow, idx) => {
    const progNodeId = `prog_${flow.id}_${idx}`;
    if (!seenPrograms.has(flow.id)) {
      seenPrograms.set(flow.id, progNodeId);
      const subType =
        flow.program_type === 'jcl' ? 'JCLUtility' :
        flow.program_type === 'sql' ? 'SQLScript' : 'COBOLProgram';
      rfNodes.push({
        id: progNodeId,
        type: 'programNode',
        position: { x: 0, y: 0 },
        data: {
          label: flow.program_name || flow.transform_name || 'Unknown',
          transform_name: flow.transform_name || flow.program_name || '',
          program_name: flow.program_name || '',
          sub_type: subType,
          language: flow.program_type,
          transform_type: flow.transform_type,
          code_snippet: flow.code_snippet,
          file_path: flow.file_path,
          confidence_score: flow.confidence_score,
          column_mappings: flow.column_mappings,
          source_entity: flow.source_entity,
          target_entity: flow.target_entity,
          flowData: flow,
        },
      });
    }
    const progRfId = seenPrograms.get(flow.id) ?? progNodeId;
    const mappingCount = flow.column_mappings.length;

    // Source entity → program  (sky blue: "reads from")
    const srcId = entityIdMap[flow.source_entity];
    if (srcId) {
      rfEdges.push({
        id: `e_${flow.id}_src`,
        source: srcId,
        target: progRfId,
        label: `reads (${mappingCount} cols)`,
        type: 'smoothstep',
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#38bdf8' },
        style: { stroke: '#38bdf8', strokeWidth: 2 },
        labelStyle: { fill: '#7dd3fc', fontSize: 9, fontFamily: 'JetBrains Mono, monospace' },
        labelBgStyle: { fill: '#0c1829', fillOpacity: 0.85 },
        labelBgPadding: [4, 2] as [number, number],
      });
    }
    // Program → target entity  (emerald: "writes to")
    const tgtId = entityIdMap[flow.target_entity];
    if (tgtId) {
      rfEdges.push({
        id: `e_${flow.id}_tgt`,
        source: progRfId,
        target: tgtId,
        label: `writes (${mappingCount} cols)`,
        type: 'smoothstep',
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#34d399' },
        style: { stroke: '#34d399', strokeWidth: 2 },
        labelStyle: { fill: '#6ee7b7', fontSize: 9, fontFamily: 'JetBrains Mono, monospace' },
        labelBgStyle: { fill: '#0c1a15', fillOpacity: 0.85 },
        labelBgPadding: [4, 2] as [number, number],
      });
    }
  });

  return { rfNodes, rfEdges };
}

// ─── detail panel (shown when a ProgramNode is selected) ───────────────────
function DetailPanel({ flow, onClose }: { flow: ColumnFlowEdge; onClose: () => void }) {
  const bgKey =
    flow.program_type === 'jcl' ? 'JCLUtility' :
    flow.program_type === 'sql' ? 'SQLScript' : 'COBOLProgram';
  const bg = ENTITY_COLOR[bgKey];

  const titleLine = flow.transform_name && flow.transform_name !== flow.program_name
    ? flow.transform_name
    : flow.program_name;
  const subtitleLine = flow.transform_name !== flow.program_name && flow.program_name
    ? `in ${flow.program_name}`
    : '';

  return (
    <div className="absolute right-0 top-0 h-full w-[26rem] border-l border-surface-border bg-surface-card overflow-y-auto z-10 shadow-2xl">
      <div style={{ backgroundColor: bg }} className="flex items-center justify-between px-4 py-3 text-white">
        <div>
          <p className="font-semibold text-sm font-mono">{titleLine}</p>
          {subtitleLine && <p className="text-[10px] opacity-70 font-mono mt-0.5">{subtitleLine}</p>}
          <p className="text-[10px] opacity-80 mt-0.5">{flow.program_type.toUpperCase()} · {flow.transform_type}</p>
        </div>
        <button onClick={onClose} className="rounded-full p-1 hover:bg-white/20"><X size={14} /></button>
      </div>

      {/* Flow summary */}
      <div className="px-4 py-3 border-b border-surface-border text-xs text-slate-400">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">From</p>
        <p className="font-mono text-sky-300 mt-0.5">{flow.source_entity}</p>
        <div className="flex items-center gap-1 my-1.5 text-slate-600"><ChevronRight size={12} /></div>
        <p className="text-[10px] uppercase tracking-wide text-slate-500">To</p>
        <p className="font-mono text-emerald-300 mt-0.5">{flow.target_entity}</p>
        <p className="mt-2 text-slate-500">Confidence: {Math.round(flow.confidence_score * 100)}%</p>
      </div>

      {/* Code snippet */}
      {flow.code_snippet && (
        <div className="px-4 py-3 border-b border-surface-border">
          <p className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-slate-500">
            <Code2 size={10} /> Code Snippet
          </p>
          <pre className="whitespace-pre-wrap rounded-lg bg-surface p-3 font-mono text-[10px] text-green-400 leading-relaxed overflow-x-auto">
            {flow.code_snippet}
          </pre>
        </div>
      )}

      {/* Column mappings table */}
      <div className="px-4 py-3">
        <p className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-slate-500">
          <Table2 size={10} /> Column Mappings ({flow.column_mappings.length})
        </p>
        {flow.column_mappings.length === 0 ? (
          <p className="text-[11px] text-slate-500 italic">No column-level mappings captured.</p>
        ) : (
          <div className="rounded-lg overflow-hidden border border-surface-border">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="bg-surface">
                  <th className="px-2 py-1.5 text-left text-slate-400 font-medium">Source Column</th>
                  <th className="px-2 py-1.5 text-left text-slate-400 font-medium">Target Column</th>
                  <th className="px-2 py-1.5 text-left text-slate-400 font-medium">Type</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {flow.column_mappings.map((cm, i) => (
                  <tr key={i} className="hover:bg-surface/50 group">
                    <td className="px-2 py-1 font-mono text-sky-400">{cm.source_col}</td>
                    <td className="px-2 py-1 font-mono text-emerald-400">{cm.target_col}</td>
                    <td className="px-2 py-1 text-slate-500">{cm.transform_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Per-mapping snippets */}
      {flow.column_mappings.some((m) => m.snippet) && (
        <div className="px-4 pb-4">
          <p className="mb-2 text-[10px] uppercase tracking-widest text-slate-500">Mapping Code</p>
          {flow.column_mappings.filter((m) => m.snippet).map((cm, i) => (
            <div key={i} className="mb-2">
              <p className="text-[10px] text-slate-400 mb-0.5">
                <span className="text-sky-400">{cm.source_col}</span>
                {' → '}
                <span className="text-emerald-400">{cm.target_col}</span>
              </p>
              <pre className="whitespace-pre-wrap rounded bg-surface px-2 py-1 font-mono text-[9px] text-green-400 overflow-x-auto">
                {cm.snippet}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── empty state ────────────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center px-8">
      <div className="rounded-full bg-primary-900/40 p-6">
        <Table2 size={32} className="text-primary-400" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-slate-200">No Column Lineage Data</h2>
        <p className="mt-1 text-sm text-slate-400 max-w-sm">
          Run the extraction pipeline to populate column-level field mappings.
        </p>
        <p className="mt-3 rounded-lg bg-surface px-3 py-2 font-mono text-xs text-slate-500 inline-block">
          make pipeline
        </p>
      </div>
    </div>
  );
}

// ─── main page ──────────────────────────────────────────────────────────────
export default function ColumnMapper() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['columnFlow'],
    queryFn: () => lineageApi.columnFlowData(),
    retry: false,
  });

  const [selectedFlow, setSelectedFlow] = useState<ColumnFlowEdge | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Build and layout graph whenever data changes
  useEffect(() => {
    if (!data) return;
    if (!data.entities?.length && !data.flows?.length) return;
    const { rfNodes, rfEdges } = buildFlowGraph(data.entities ?? [], data.flows ?? []);
    const laidOut = applyDagreLayout(rfNodes, rfEdges);
    setNodes(laidOut);
    setEdges(rfEdges);
  }, [data, setNodes, setEdges]);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (node.type === 'programNode' && node.data.flowData) {
        setSelectedFlow(node.data.flowData as ColumnFlowEdge);
      }
    },
    [],
  );

  const noData =
    !isLoading &&
    !error &&
    (!data || ((!data.entities || data.entities.length === 0) && (!data.flows || data.flows.length === 0)));

  const stats = useMemo(() => {
    if (!data) return null;
    const totalMappings = (data.flows ?? []).reduce((s, f) => s + f.column_mappings.length, 0);
    return { entities: data.entities?.length ?? 0, flows: data.flows?.length ?? 0, mappings: totalMappings };
  }, [data]);

  return (
    <div className="relative flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-surface-border bg-surface-card px-4 py-2 flex-shrink-0">
        <Table2 size={16} className="text-primary-400" />
        <h1 className="text-sm font-semibold text-slate-200">Column Data Lineage</h1>
        <span className="text-xs text-slate-500">End-to-end field-level mapping from source to target</span>
        {stats && (
          <div className="ml-auto flex items-center gap-3 text-[11px]">
            <span className="text-slate-400">{stats.entities} entities</span>
            <span className="text-slate-600">·</span>
            <span className="text-slate-400">{stats.flows} transform steps</span>
            <span className="text-slate-600">·</span>
            <span className="text-primary-400 font-semibold">{stats.mappings} column mappings</span>
          </div>
        )}
      </div>

      {/* Body */}
      <div className="relative flex-1 overflow-hidden">
        {isLoading && (
          <div className="flex h-full items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-500 border-t-transparent" />
          </div>
        )}
        {noData && <EmptyState />}
        {error && (
          <div className="flex h-full items-center justify-center text-sm text-red-400">
            {String(error)}
          </div>
        )}
        {!isLoading && !noData && !error && (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.1}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#1e293b" gap={20} />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(n) => ENTITY_COLOR[n.data?.sub_type as string] ?? '#374151'}
              maskColor="rgba(0,0,0,0.6)"
              style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b' }}
            />
          </ReactFlow>
        )}

        {/* Detail panel */}
        {selectedFlow && (
          <DetailPanel flow={selectedFlow} onClose={() => setSelectedFlow(null)} />
        )}
      </div>
    </div>
  );
}
