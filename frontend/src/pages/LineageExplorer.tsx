import React, { useState, useMemo, useCallback, useEffect } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type NodeMouseHandler,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import type { Node } from 'reactflow';
import { Search, RefreshCw } from 'lucide-react';

import { useLineageGraph, useTriggerExtraction, useJobStatus } from '@/hooks/useLineage';
import { buildReactFlowGraph, nodeColour } from '@/utils/graphLayout';
import type { LineageNode } from '@/types/lineage';
import DAGNode from '@/components/DAGNode';
import NodeDetailPanel from '@/components/NodeDetailPanel';

const NODE_TYPES = { lineageNode: DAGNode };

export default function LineageExplorer() {
  const { data: graph, isLoading, isError, refetch } = useLineageGraph();
  const [selectedNode, setSelectedNode] = useState<LineageNode | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [repoPath, setRepoPath] = useState('./mock_code');

  const triggerExtraction = useTriggerExtraction();
  const [jobId, setJobId] = useState<string | null>(null);
  const jobStatus = useJobStatus(jobId);

  const { nodes: layoutNodes, edges: layoutEdges } = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    const filtered = searchTerm
      ? {
          ...graph,
          nodes: graph.nodes.filter((n) =>
            n.name.toLowerCase().includes(searchTerm.toLowerCase()),
          ),
        }
      : graph;
    return buildReactFlowGraph(filtered.nodes, filtered.edges);
  }, [graph, searchTerm]);

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges);

  // useNodesState / useEdgesState initialise once at mount (when the query
  // hasn't resolved yet and layoutNodes is []). Sync whenever the computed
  // layout changes so the graph actually appears after the API responds.
  useEffect(() => { setNodes(layoutNodes); }, [layoutNodes, setNodes]);
  useEffect(() => { setEdges(layoutEdges); }, [layoutEdges, setEdges]);

  const onNodeClick = useCallback<NodeMouseHandler>(
    (_event, node: Node) => {
      const lineageNode = (node.data as { lineageNode: LineageNode }).lineageNode;
      setSelectedNode(lineageNode);
    },
    [],
  );

  const handleExtract = async () => {
    const job = await triggerExtraction.mutateAsync(repoPath);
    setJobId(job.job_id);
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-500 border-t-transparent" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-slate-400">
        <p>Failed to load lineage graph. Is the backend running?</p>
        <button
          onClick={() => void refetch()}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-3 border-b border-surface-border bg-surface-card px-4 py-2">
        <h1 className="text-sm font-semibold text-slate-200">Lineage Explorer</h1>
        <span className="text-xs text-slate-500">
          {graph?.nodes.length ?? 0} nodes · {graph?.edges.length ?? 0} edges
        </span>

        {/* Search */}
        <div className="ml-auto flex items-center gap-1 rounded-lg border border-surface-border bg-surface px-2 py-1">
          <Search size={14} className="text-slate-500" />
          <input
            className="w-40 bg-transparent text-xs text-slate-300 placeholder-slate-500 outline-none"
            placeholder="Filter nodes…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        {/* Extract button */}
        <div className="flex items-center gap-1">
          <input
            className="w-40 rounded-lg border border-surface-border bg-surface px-2 py-1 text-xs text-slate-300 outline-none"
            placeholder="Repo path"
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
          />
          <button
            onClick={() => void handleExtract()}
            disabled={triggerExtraction.isPending}
            className="flex items-center gap-1 rounded-lg bg-primary-600 px-3 py-1 text-xs text-white hover:bg-primary-700 disabled:opacity-50"
          >
            <RefreshCw size={12} className={triggerExtraction.isPending ? 'animate-spin' : ''} />
            Extract
          </button>
        </div>

        {/* Job status badge */}
        {jobStatus.data && (
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              jobStatus.data.status === 'complete'
                ? 'bg-emerald-800 text-emerald-200'
                : jobStatus.data.status === 'failed'
                ? 'bg-red-800 text-red-200'
                : 'bg-amber-800 text-amber-200'
            }`}
          >
            {jobStatus.data.status}
          </span>
        )}
      </div>

      {/* React Flow canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          fitView
          minZoom={0.1}
          proOptions={{ hideAttribution: true }}
          className="bg-surface"
        >
          <Background color="#1e293b" gap={20} />
          <Controls className="bg-surface-card border-surface-border" />
          <MiniMap
            nodeColor={(n) => {
              const ln = (n.data as { lineageNode: LineageNode }).lineageNode;
              return ln ? nodeColour(ln.sub_type).replace('bg-', '#').replace('-700', '').replace('-600', '') : '#475569';
            }}
            className="!bg-surface-card !border-surface-border"
          />
        </ReactFlow>
      </div>

      {/* Node detail panel */}
      {selectedNode && (
        <NodeDetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}
    </div>
  );
}
