import React, { useState } from 'react';
import { CheckCircle, XCircle, AlertCircle, Clock, MessageSquare, ExternalLink, Activity } from 'lucide-react';

const RAG_URL = (typeof import.meta !== 'undefined' && (import.meta as { env?: Record<string, string> }).env?.VITE_RAG_URL) || 'http://localhost:8501';
const JAEGER_URL = 'http://localhost:16686';
import {
  useEvaluationReport,
  useHumanReviewQueue,
  useSubmitReview,
} from '@/hooks/useLineage';
import type { HumanReviewItem } from '@/types/lineage';

function MetricCard({
  label,
  value,
  colour,
}: {
  label: string;
  value: number | undefined;
  colour: string;
}) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <p className="text-[10px] uppercase tracking-widest text-slate-500">{label}</p>
      <p className={`mt-1 text-3xl font-bold ${colour}`}>
        {value !== undefined ? `${(value * 100).toFixed(1)}%` : '—'}
      </p>
    </div>
  );
}

function ReviewRow({
  item,
  onDecide,
}: {
  item: HumanReviewItem;
  onDecide: (id: string, decision: 'approved' | 'rejected') => void;
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="truncate font-mono text-xs font-semibold text-slate-200">
            {item.file_path}
          </p>
          <p className="mt-1 text-[11px] text-slate-400">{item.assertion}</p>
          <p className="mt-0.5 text-[10px] text-slate-500">{item.reason}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <span className="rounded bg-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
            {Math.round(item.confidence * 100)}%
          </span>
          {item.status === 'pending' ? (
            <>
              <button
                onClick={() => onDecide(item.id, 'approved')}
                className="rounded bg-emerald-800 p-1 hover:bg-emerald-700"
                title="Approve"
              >
                <CheckCircle size={14} className="text-emerald-300" />
              </button>
              <button
                onClick={() => onDecide(item.id, 'rejected')}
                className="rounded bg-red-900 p-1 hover:bg-red-800"
                title="Reject"
              >
                <XCircle size={14} className="text-red-300" />
              </button>
            </>
          ) : (
            <span
              className={`text-[10px] font-semibold ${
                item.status === 'approved' ? 'text-emerald-400' : 'text-red-400'
              }`}
            >
              {item.status}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const { data: report, isLoading: reportLoading } = useEvaluationReport();
  const { data: queue } = useHumanReviewQueue();
  const submitReview = useSubmitReview();
  const [filter, setFilter] = useState<'all' | 'pending'>('pending');

  const handleDecide = (id: string, decision: 'approved' | 'rejected') => {
    void submitReview.mutate({ id, decision });
  };

  const filteredQueue =
    queue?.filter((i) => (filter === 'pending' ? i.status === 'pending' : true)) ?? [];

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-surface-border bg-surface-card px-4 py-2">
        <h1 className="text-sm font-semibold text-slate-200">Admin Dashboard</h1>
      </div>

      <div className="space-y-6 p-6">
        {/* Quick links: RAG assistant + Jaeger traces */}
        <section className="flex flex-wrap gap-3">
          <a
            href={RAG_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 rounded-xl border border-primary-700 bg-primary-900/40 px-4 py-3 text-sm font-medium text-primary-300 transition-colors hover:border-primary-500 hover:bg-primary-800/60"
          >
            <MessageSquare size={16} />
            Open RAG Assistant
            <ExternalLink size={12} className="opacity-60" />
          </a>
          <a
            href={JAEGER_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/40 px-4 py-3 text-sm font-medium text-slate-300 transition-colors hover:border-slate-500 hover:bg-slate-700/60"
          >
            <Activity size={16} />
            Jaeger Traces
            <ExternalLink size={12} className="opacity-60" />
          </a>
        </section>

        {/* Evaluation metrics */}
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-400">
            Evaluation Metrics
          </h2>
          {reportLoading ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : !report ? (
            <p className="text-xs text-slate-500">No evaluation report available.</p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetricCard
                label="L1 Precision"
                value={report.level1?.precision}
                colour="text-sky-400"
              />
              <MetricCard
                label="L1 Recall"
                value={report.level1?.recall}
                colour="text-violet-400"
              />
              <MetricCard
                label="L2 F1"
                value={report.level2?.f1}
                colour="text-emerald-400"
              />
              <MetricCard
                label="L3 E2E Coverage"
                value={report.level3?.end_to_end_coverage}
                colour="text-amber-400"
              />
            </div>
          )}
        </section>

        {/* Human review queue */}
        <section>
          <div className="mb-3 flex items-center gap-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
              Human Review Queue
            </h2>
            <div className="flex rounded-lg border border-surface-border bg-surface text-[11px]">
              {(['pending', 'all'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-2 py-0.5 capitalize ${
                    filter === f
                      ? 'bg-primary-600 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
            <span className="ml-auto flex items-center gap-1 text-xs text-slate-500">
              <Clock size={12} />
              {filteredQueue.filter((i) => i.status === 'pending').length} pending
            </span>
          </div>

          {filteredQueue.length === 0 ? (
            <div className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card p-4 text-xs text-slate-500">
              <AlertCircle size={16} />
              {filter === 'pending' ? 'No items pending review.' : 'Queue is empty.'}
            </div>
          ) : (
            <div className="space-y-2">
              {filteredQueue.map((item) => (
                <ReviewRow key={item.id} item={item} onDecide={handleDecide} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
