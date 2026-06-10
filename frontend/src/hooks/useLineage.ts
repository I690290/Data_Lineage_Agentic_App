// ============================================================
// TanStack Query hooks for data fetching
// ============================================================
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { lineageApi, extractionApi, ragApi, evaluationApi } from '@/api/client';

export const QUERY_KEYS = {
  graph: ['lineage', 'graph'] as const,
  impact: (nodeId: string) => ['lineage', 'impact', nodeId] as const,
  path: (s: string, t: string) => ['lineage', 'path', s, t] as const,
  search: (q: string) => ['lineage', 'search', q] as const,
  jobStatus: (id: string) => ['extraction', 'job', id] as const,
  evalReport: ['evaluation', 'report'] as const,
  humanReview: ['evaluation', 'human-review'] as const,
};

// ── Lineage ──────────────────────────────────────────────────
export function useLineageGraph() {
  return useQuery({
    queryKey: QUERY_KEYS.graph,
    queryFn: lineageApi.getGraph,
    staleTime: 1000 * 60 * 2,
  });
}

export function useImpactAnalysis(nodeId: string | null) {
  return useQuery({
    queryKey: QUERY_KEYS.impact(nodeId ?? ''),
    queryFn: () => lineageApi.getUpstreamDownstream(nodeId!),
    enabled: !!nodeId,
    staleTime: 1000 * 60,
  });
}

export function useLineageSearch(query: string) {
  return useQuery({
    queryKey: QUERY_KEYS.search(query),
    queryFn: () => lineageApi.searchNodes(query),
    enabled: query.length > 2,
    staleTime: 1000 * 30,
  });
}

// ── Extraction ────────────────────────────────────────────────
export function useTriggerExtraction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: extractionApi.triggerExtraction,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.graph });
    },
  });
}

export function useJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: QUERY_KEYS.jobStatus(jobId ?? ''),
    queryFn: () => extractionApi.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (data) =>
      data?.status === 'running' || data?.status === 'queued' ? 2000 : false,
  });
}

// ── RAG ───────────────────────────────────────────────────────
export function useRAGQuery() {
  return useMutation({ mutationFn: ragApi.query });
}

// ── Evaluation ────────────────────────────────────────────────
export function useEvaluationReport() {
  return useQuery({
    queryKey: QUERY_KEYS.evalReport,
    queryFn: evaluationApi.getReport,
    staleTime: 1000 * 60 * 5,
  });
}

export function useHumanReviewQueue() {
  return useQuery({
    queryKey: QUERY_KEYS.humanReview,
    queryFn: evaluationApi.getHumanReviewQueue,
    refetchInterval: 10000,
  });
}

export function useSubmitReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, notes }: { id: string; decision: 'approved' | 'rejected'; notes?: string }) =>
      evaluationApi.submitReview(id, decision, notes),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.humanReview });
    },
  });
}
