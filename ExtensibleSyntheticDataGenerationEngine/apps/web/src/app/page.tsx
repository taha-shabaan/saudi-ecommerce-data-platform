'use client';

import React from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { Header } from '../components/Header';
import { LocalesSelector } from '../components/LocalesSelector';
import { ConsistencyPolicyPanel } from '../components/ConsistencyPolicyPanel';
import { ResourceSinksPanel } from '../components/ResourceSinksPanel';
import { EntityList } from '../components/EntityList';
import { EntityInspector } from '../components/EntityInspector';
import { ResultsViewer } from '../components/ResultsViewer';
import { ApiExplorer } from '../components/ApiExplorer';
import { AlertTriangle, CheckCircle, Network } from 'lucide-react';

export default function Home() {
  const { activeTab, validateDAG } = useSchemaStore();
  const dag = validateDAG();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-6 space-y-6">
        
        {/* TAB 1: SCHEMA BUILDER CANVAS */}
        {activeTab === 'builder' && (
          <div className="space-y-6">
            
            {/* Top Configuration Grid: Locales, Inconsistency, Sinks */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-1">
                <LocalesSelector />
              </div>
              <div className="lg:col-span-2">
                <ConsistencyPolicyPanel />
              </div>
            </div>

            <ResourceSinksPanel />

            {/* DAG Validation & Execution Sequence Bar */}
            <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Network className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    Client-Side Topological DAG Validation
                  </span>
                </div>

                <div>
                  {dag.isValid ? (
                    <span className="px-2.5 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                      <CheckCircle className="w-3 h-3" />
                      <span>DAG VALID — Order: {dag.order.join(' ➔ ')}</span>
                    </span>
                  ) : (
                    <span className="px-2.5 py-0.5 rounded text-[11px] font-mono font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      <span>CYCLE ERROR — Generation Blocked</span>
                    </span>
                  )}
                </div>
              </div>

              {!dag.isValid && (
                <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs font-mono">
                  {dag.errorMessage}
                </div>
              )}
            </div>

            {/* Entity Canvas: Left Sidebar + Right Inspector */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-start">
              <div className="lg:col-span-1">
                <EntityList />
              </div>
              <div className="lg:col-span-3">
                <EntityInspector />
              </div>
            </div>

          </div>
        )}

        {/* TAB 2: EXPORT ARTIFACT RESULTS */}
        {activeTab === 'results' && <ResultsViewer />}

        {/* TAB 3: DYNAMIC MOCK API EXPLORER */}
        {activeTab === 'api-explorer' && <ApiExplorer />}

      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 px-6 py-4 text-center text-xs text-slate-600">
        Extensible Synthetic Data Generation Engine • Production Architecture • Next.js + FastAPI + DuckDB
      </footer>
    </div>
  );
}
