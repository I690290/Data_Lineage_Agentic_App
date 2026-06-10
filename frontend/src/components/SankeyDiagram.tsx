import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { sankey, sankeyLinkHorizontal, SankeyNode, SankeyLink } from 'd3-sankey';

export interface SankeyNodeData {
  id: string;
  name: string;
  type: 'source' | 'transformation' | 'target';
  confidence?: number;
  metadata?: Record<string, unknown>;
}

export interface SankeyLinkData {
  source: string;
  target: string;
  value: number;
  transformationType?: string;
  expression?: string;
  confidence?: number;
}

interface SankeyDiagramProps {
  nodes: SankeyNodeData[];
  links: SankeyLinkData[];
  width?: number;
  height?: number;
  onNodeClick?: (node: SankeyNodeData) => void;
}

type D3SankeyNode = SankeyNode<SankeyNodeData, SankeyLinkData>;
type D3SankeyLink = SankeyLink<SankeyNodeData, SankeyLinkData>;

/** SankeyDiagram — column-level lineage as a Sankey / flow diagram using D3. */
export default function SankeyDiagram({
  nodes,
  links,
  width = 900,
  height = 500,
  onNodeClick,
}: SankeyDiagramProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = { top: 10, right: 10, bottom: 10, left: 10 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    // Build index maps
    const nodeIndex = new Map(nodes.map((n, i) => [n.id, i]));
    const sankeyNodes: D3SankeyNode[] = nodes.map((n) => ({ ...n } as D3SankeyNode));
    const sankeyLinks: D3SankeyLink[] = links
      .filter((l) => nodeIndex.has(l.source) && nodeIndex.has(l.target))
      .map((l) => ({
        source: nodeIndex.get(l.source) as number,
        target: nodeIndex.get(l.target) as number,
        value: l.value || 1,
        transformationType: l.transformationType,
        expression: l.expression,
        confidence: l.confidence,
      } as D3SankeyLink));

    const sankeyLayout = sankey<SankeyNodeData, SankeyLinkData>()
      .nodeWidth(22)
      .nodePadding(12)
      .extent([[0, 0], [innerW, innerH]]);

    const { nodes: laidOutNodes, links: laidOutLinks } = sankeyLayout({
      nodes: sankeyNodes,
      links: sankeyLinks,
    });

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Links
    g.append('g')
      .attr('fill', 'none')
      .selectAll('path')
      .data(laidOutLinks)
      .join('path')
      .attr('d', sankeyLinkHorizontal())
      .attr('stroke', (d) => confidenceColour((d as SankeyLinkData).confidence ?? 1))
      .attr('stroke-width', (d) => Math.max(1, (d as D3SankeyLink).width ?? 1))
      .attr('stroke-opacity', 0.4)
      .attr('class', 'cursor-pointer transition-opacity hover:opacity-80')
      .append('title')
      .text(
        (d) =>
          `${(d.source as D3SankeyNode).name} → ${(d.target as D3SankeyNode).name}\n${
            (d as SankeyLinkData).transformationType ?? ''
          }`,
      );

    // Nodes
    const nodeG = g
      .append('g')
      .selectAll('g')
      .data(laidOutNodes)
      .join('g')
      .attr('class', 'cursor-pointer')
      .on('click', (_event, d) => onNodeClick?.(d as SankeyNodeData));

    nodeG
      .append('rect')
      .attr('x', (d) => d.x0 ?? 0)
      .attr('y', (d) => d.y0 ?? 0)
      .attr('width', (d) => (d.x1 ?? 0) - (d.x0 ?? 0))
      .attr('height', (d) => Math.max(1, (d.y1 ?? 0) - (d.y0 ?? 0)))
      .attr('fill', (d) => nodeColour((d as SankeyNodeData).type))
      .attr('rx', 3)
      .attr('opacity', 0.85);

    nodeG
      .append('text')
      .attr('x', (d) => ((d.x0 ?? 0) < innerW / 2 ? (d.x1 ?? 0) + 6 : (d.x0 ?? 0) - 6))
      .attr('y', (d) => ((d.y0 ?? 0) + (d.y1 ?? 0)) / 2)
      .attr('dy', '0.35em')
      .attr('text-anchor', (d) => ((d.x0 ?? 0) < innerW / 2 ? 'start' : 'end'))
      .attr('fill', '#cbd5e1')
      .attr('font-size', '10px')
      .text((d) => truncate((d as SankeyNodeData).name, 20));
  }, [nodes, links, width, height, onNodeClick]);

  if (nodes.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-slate-500">
        No column lineage data available.
      </div>
    );
  }

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className="overflow-visible rounded-lg bg-surface"
    />
  );
}

function confidenceColour(score: number): string {
  if (score >= 0.9) return '#10b981';
  if (score >= 0.7) return '#f59e0b';
  return '#ef4444';
}

function nodeColour(type: SankeyNodeData['type']): string {
  switch (type) {
    case 'source':         return '#3b82f6';
    case 'transformation': return '#f97316';
    case 'target':         return '#22c55e';
    default:               return '#64748b';
  }
}

function truncate(str: string, maxLen: number): string {
  return str.length > maxLen ? `${str.slice(0, maxLen - 1)}…` : str;
}
