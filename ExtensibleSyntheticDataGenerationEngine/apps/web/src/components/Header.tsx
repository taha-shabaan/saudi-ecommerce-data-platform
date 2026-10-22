import React from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { STARTER_TEMPLATES } from '../lib/templates';
import { Sparkles, Database, FileSpreadsheet, Server, RefreshCw } from 'lucide-react';

export const Header: React.FC = () => {
  const {
    activeTab,
    setActiveTab,
    generateData,
    isGenerating,
    loadTemplate,
    validateDAG,
    generationResult
  } = useSchemaStore();

  const dag = validateDAG();

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-40 px-6 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 font-bold text-lg">
            ⚡
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-white tracking-tight">
                Synthetic Data Engine
              </h1>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/20 border border-cyan-500/40 text-cyan-300">
                v1.0.0
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Relational DAGs • Multi-Locale Coherence • 6 Target Resource Sinks
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-medium">
          <button
            onClick={() => setActiveTab('builder')}
            className={`px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${
              activeTab === 'builder'
                ? 'bg-slate-800 text-emerald-400 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            <span>Schema Canvas</span>
          </button>

          <button
            onClick={() => setActiveTab('results')}
            className={`px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${
              activeTab === 'results'
                ? 'bg-slate-800 text-emerald-400 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>Export Artifacts</span>
            {generationResult && (
              <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('api-explorer')}
            className={`px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${
              activeTab === 'api-explorer'
                ? 'bg-slate-800 text-cyan-400 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Server className="w-3.5 h-3.5" />
            <span>Mock API Explorer</span>
          </button>
        </div>

        {/* Right Actions: Templates & Generate Button */}
        <div className="flex items-center gap-3">
          {/* Templates Dropdown */}
          <select
            onChange={(e) => {
              if (e.target.value) loadTemplate(e.target.value);
            }}
            defaultValue=""
            className="text-xs bg-slate-800 border border-slate-700 text-slate-200 rounded-md px-2.5 py-1.5 font-medium hover:border-slate-600 transition"
          >
            <option value="" disabled>
              Load Starter Template...
            </option>
            {STARTER_TEMPLATES.map((tmpl) => (
              <option key={tmpl.id} value={tmpl.id}>
                {tmpl.icon} {tmpl.name}
              </option>
            ))}
          </select>

          {/* Generate Button */}
          <button
            onClick={generateData}
            disabled={isGenerating || !dag.isValid}
            className={`text-xs px-4 py-2 rounded-lg font-semibold shadow-lg transition flex items-center gap-2 ${
              isGenerating || !dag.isValid
                ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/30'
            }`}
          >
            {isGenerating ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Generating...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5 text-emerald-200" />
                <span>Generate Synthetic Data</span>
              </>
            )}
          </button>
        </div>

      </div>
    </header>
  );
};
