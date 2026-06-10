import React, { useState } from 'react';
import { GitBranch, Map, LayoutDashboard, MessageSquare, ExternalLink } from 'lucide-react';
import LineageExplorer from '@/pages/LineageExplorer';
import ColumnMapper from '@/pages/ColumnMapper';
import AdminDashboard from '@/pages/AdminDashboard';

type Tab = 'explorer' | 'mapper' | 'admin';

const TABS: { id: Tab; label: string; Icon: React.ElementType }[] = [
  { id: 'explorer', label: 'Lineage Explorer', Icon: GitBranch },
  { id: 'mapper', label: 'Column Data Lineage', Icon: Map },
  { id: 'admin', label: 'Admin', Icon: LayoutDashboard },
];

/** URL of the Streamlit RAG chat assistant (default: localhost:8501). */
const RAG_URL: string =
  (typeof import.meta !== 'undefined' && (import.meta as { env?: Record<string, string> }).env?.VITE_RAG_URL) ||
  'http://localhost:8501';

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('explorer');

  return (
    <div className="flex h-screen flex-col bg-surface font-['Inter',sans-serif] text-slate-100">
      {/* Top nav */}
      <nav className="flex items-center gap-1 border-b border-surface-border bg-surface-card px-4">
        {/* Logo */}
        <div className="mr-4 flex items-center gap-2 py-3">
          <GitBranch size={20} className="text-primary-500" />
          <span className="font-semibold text-slate-200">
            Data Lineage Explorer
          </span>
          <span className="ml-1 rounded bg-primary-900 px-1.5 py-0.5 text-[10px] font-bold text-primary-300">
            Credit Risk
          </span>
        </div>

        {/* Tabs */}
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-1.5 border-b-2 px-3 py-3 text-xs font-medium transition-colors
              ${
                activeTab === id
                  ? 'border-primary-500 text-primary-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}

        {/* RAG Assistant link → Streamlit */}
        <a
          href={RAG_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-primary-700 bg-primary-900/40 px-3 py-1.5 text-xs font-medium text-primary-300 transition-colors hover:border-primary-500 hover:bg-primary-800/60 hover:text-primary-200"
          title={`Open RAG Assistant at ${RAG_URL}`}
        >
          <MessageSquare size={13} />
          Ask AI
          <ExternalLink size={11} className="opacity-60" />
        </a>
      </nav>

      {/* Page */}
      <main className="flex-1 overflow-hidden">
        {activeTab === 'explorer' && <LineageExplorer />}
        {activeTab === 'mapper' && <ColumnMapper />}
        {activeTab === 'admin' && <AdminDashboard />}
      </main>
    </div>
  );
}
