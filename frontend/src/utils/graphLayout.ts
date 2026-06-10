// ============================================================
// Graph layout utilities using dagre
// ============================================================
import dagre from 'dagre';
import type { Node, Edge } from 'reactflow';
import type { LineageNode, LineageEdge } from '@/types/lineage';

export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 80;

/** Map node sub-type to Tailwind colour class for the DAG nodes */
export function nodeColour(subType: string): string {
  const map: Record<string, string> = {
    DB2Table: 'bg-violet-700',
    OracleTable: 'bg-emerald-700',
    OracleExternalTable: 'bg-amber-700',
    OracleView: 'bg-teal-700',
    MainframeDataset: 'bg-sky-700',
    XMLFile: 'bg-orange-600',
    COBOLProgram: 'bg-blue-700',
    JCLUtility: 'bg-indigo-700',
    SQLScript: 'bg-lime-700',
    JavaClass: 'bg-rose-700',
  };
  return map[subType] ?? 'bg-slate-600';
}

/** Map node sub-type to a short label used in the legend */
export function nodeLabel(subType: string): string {
  const map: Record<string, string> = {
    DB2Table: 'DB2',
    OracleTable: 'ORA',
    OracleExternalTable: 'EXT',
    OracleView: 'VW',
    MainframeDataset: 'DS',
    XMLFile: 'XML',
    COBOLProgram: 'CBL',
    JCLUtility: 'JCL',
    SQLScript: 'SQL',
    JavaClass: 'JAVA',
  };
  return map[subType] ?? '?';
}

/**
 * Convert domain LineageNode/LineageEdge arrays to React Flow nodes/edges
 * with dagre-computed layout.
 */
export function buildReactFlowGraph(
  lineageNodes: LineageNode[],
  lineageEdges: LineageEdge[],
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', ranksep: 80, nodesep: 40 });

  lineageNodes.forEach((n) => {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });
  lineageEdges.forEach((e) => {
    g.setEdge(e.source, e.target);
  });

  dagre.layout(g);

  const nodes: Node[] = lineageNodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      type: 'lineageNode',
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { lineageNode: n },
    };
  });

  const edges: Edge[] = lineageEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.relationship,
    animated: e.relationship === 'WRITES_TO',
    style: { stroke: '#64748b' },
    labelStyle: { fill: '#94a3b8', fontSize: 10 },
    data: { lineageEdge: e },
  }));

  return { nodes, edges };
}
