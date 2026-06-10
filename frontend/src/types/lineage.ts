// ============================================================
// TypeScript types for Data Lineage Explorer
// ============================================================

export type NodeType =
  | 'DataSource'
  | 'Dataset'
  | 'TransformationUnit'
  | 'OracleExternalTable'
  | 'OracleView';

export type NodeSubType =
  | 'DB2Table'
  | 'OracleTable'
  | 'OracleExternalTable'
  | 'OracleView'
  | 'MainframeDataset'
  | 'XMLFile'
  | 'COBOLProgram'
  | 'JCLUtility'
  | 'SQLScript'
  | 'JavaClass';

export type RelationshipType =
  | 'READS_FROM'
  | 'WRITES_TO'
  | 'TRANSFORMS_VIA'
  | 'MAPS_TO'
  | 'CALLS';

export interface LineageNode {
  id: string;
  type: NodeType;
  sub_type: NodeSubType;
  name: string;
  system?: string;
  language?: string;
  schema?: string;
  table?: string;
  description?: string;
  columns?: string[];
  copybooks?: string[];
  confidence?: number;
  properties?: Record<string, unknown>;
}

export interface LineageEdge {
  id: string;
  source: string;
  target: string;
  relationship: RelationshipType;
  mechanism?: string;
  confidence?: number;
  column_mappings?: ColumnMapping[];
}

export interface ColumnMapping {
  source_column: string;
  target_column: string;
  transform?: string;
}

export interface LineageGraph {
  nodes: LineageNode[];
  edges: LineageEdge[];
  flow_name?: string;
  system?: string;
  generated_at?: string;
}

export interface UpstreamDownstream {
  node_id: string;
  upstream: LineageNode[];
  downstream: LineageNode[];
  upstream_edges: LineageEdge[];
  downstream_edges: LineageEdge[];
}

export interface EndToEndPath {
  source_id: string;
  target_id: string;
  path: LineageNode[];
  edges: LineageEdge[];
}

export interface EvaluationReport {
  run_id: string;
  timestamp: string;
  level1?: {
    precision: number;
    recall: number;
    f1: number;
  };
  level2?: {
    files_processed: number;
    hallucination_rate: number;
    precision: number;
    recall: number;
    f1: number;
  };
  level3?: {
    overall_precision: number;
    overall_recall: number;
    overall_f1: number;
    end_to_end_coverage: number;
  };
  human_review_queue?: HumanReviewItem[];
}

export interface HumanReviewItem {
  id: string;
  file_path: string;
  assertion: string;
  confidence: number;
  reason: string;
  status: 'pending' | 'approved' | 'rejected';
}

export interface ExtractionJob {
  job_id: string;
  status: 'queued' | 'running' | 'complete' | 'failed';
  repo_path: string;
  started_at?: string;
  completed_at?: string;
  files_processed?: number;
  nodes_extracted?: number;
  edges_extracted?: number;
  errors?: string[];
}

export interface RAGResponse {
  query: string;
  answer: string;
  sources: RAGSource[];
  confidence: number;
}

export interface RAGSource {
  file_path: string;
  chunk_id: string;
  score: number;
  content_preview: string;
}

// ---- Column Data Lineage types ----

export interface ColumnFlowMapping {
  source_col: string;
  target_col: string;
  transform_type: string;
  snippet: string;
}

export interface ColumnFlowEdge {
  id: string;
  source_entity: string;
  target_entity: string;
  program_name: string;     // file stem, e.g. CRDB2EXT or MI4014_EXT_TABLE
  transform_name: string;   // paragraph/step name, e.g. OPEN-CURSOR-PARA
  program_type: string;     // 'cobol' | 'jcl' | 'sql'
  transform_type: string;
  code_snippet: string;
  file_path: string;
  confidence_score: number;
  column_mappings: ColumnFlowMapping[];
}

export interface ColumnFlowEntity {
  id: string;
  name: string;
  type: NodeSubType;
  system: string;
  columns: string[];
}

export interface ColumnFlowGraph {
  entities: ColumnFlowEntity[];
  flows: ColumnFlowEdge[];
}
