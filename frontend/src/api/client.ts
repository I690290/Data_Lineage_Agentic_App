// ============================================================
// API client — thin fetch wrappers for the FastAPI backend
// Routes are mounted at /api/* — vite.config.ts proxies /api → :8000
// ============================================================
import type {
  LineageGraph,
  UpstreamDownstream,
  EndToEndPath,
  ColumnFlowGraph,
  EvaluationReport,
  HumanReviewItem,
  ExtractionJob,
  RAGResponse,
} from '@/types/lineage';

const BASE = '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path}: ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API ${path}: ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ── Lineage ──────────────────────────────────────────────────
export const lineageApi = {
  getGraph: (): Promise<LineageGraph> =>
    get('/lineage/graph'),

  getUpstreamDownstream: (nodeId: string): Promise<UpstreamDownstream> =>
    get(`/lineage/impact/${encodeURIComponent(nodeId)}`),

  getEndToEndPath: (sourceId: string, targetId: string): Promise<EndToEndPath> =>
    get(`/lineage/end-to-end?source=${encodeURIComponent(sourceId)}&target=${encodeURIComponent(targetId)}`),

  getColumnLineage: (table: string, column: string): Promise<LineageGraph> =>
    get(`/lineage/column/${encodeURIComponent(table)}/${encodeURIComponent(column)}`),

  columnFlowData: (): Promise<ColumnFlowGraph> =>
    get('/lineage/columns/flow'),

  searchNodes: (q: string): Promise<LineageGraph> =>
    get(`/lineage/search?q=${encodeURIComponent(q)}`),
};

// ── Extraction ────────────────────────────────────────────────
export const extractionApi = {
  triggerExtraction: (repoPath: string): Promise<ExtractionJob> =>
    post('/lineage/extract', { repo_path: repoPath, use_new_pipeline: true }),

  getJobStatus: (jobId: string): Promise<ExtractionJob> =>
    get(`/lineage/extract/${jobId}/status`),
};

// ── RAG ───────────────────────────────────────────────────────
export const ragApi = {
  // POST /api/rag/query  body: { question: string }
  query: (question: string): Promise<RAGResponse> =>
    post('/rag/query', { question }),
};

// ── Evaluation ────────────────────────────────────────────────
export const evaluationApi = {
  getReport: (): Promise<EvaluationReport> =>
    get('/eval/report'),

  getHumanReviewQueue: (): Promise<HumanReviewItem[]> =>
    get('/eval/human-review'),

  submitReview: (
    itemId: string,
    decision: 'approved' | 'rejected',
    notes?: string,
  ): Promise<{ ok: boolean }> =>
    post(`/eval/human-review/${itemId}`, { decision, notes }),
};
