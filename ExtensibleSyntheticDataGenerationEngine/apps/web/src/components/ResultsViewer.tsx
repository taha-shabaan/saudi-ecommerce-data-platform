import React from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { Download, CheckCircle, Clock, Database, Layers, ExternalLink } from 'lucide-react';

export const ResultsViewer: React.FC = () => {
  const { generationResult, isGenerating, error, setActiveTab } = useSchemaStore();

  if (isGenerating) {
    return (
      <div className="p-12 text-center rounded-xl bg-slate-900 border border-slate-800 space-y-3">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-emerald-500 border-r-transparent"></div>
        <p className="text-sm font-semibold text-white">Generating Synthetic Datasets...</p>
        <p className="text-xs text-slate-400">Resolving DAG topological orders and packaging export artifacts.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 space-y-2">
        <h3 className="text-sm font-bold flex items-center gap-2">
          <span>Generation Failed</span>
        </h3>
        <p className="text-xs font-mono">{error}</p>
        <button
          onClick={() => setActiveTab('builder')}
          className="mt-3 text-xs px-3 py-1.5 rounded bg-rose-900/60 hover:bg-rose-800 text-white font-medium"
        >
          Return to Schema Builder
        </button>
      </div>
    );
  }

  if (!generationResult) {
    return (
      <div className="p-12 text-center rounded-xl bg-slate-900 border border-slate-800 space-y-3 text-slate-500">
        <p className="text-sm">No datasets generated yet.</p>
        <button
          onClick={() => setActiveTab('builder')}
          className="text-xs px-3 py-1.5 rounded bg-emerald-600 text-white font-medium hover:bg-emerald-500"
        >
          Open Schema Canvas to Generate
        </button>
      </div>
    );
  }

  const { schema_id, metrics, execution_order, artifacts } = generationResult;
  const baseUrl = 'http://localhost:8000';

  return (
    <div className="space-y-6">
      
      {/* Metrics Banner */}
      <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-emerald-400" />
            <h2 className="text-sm font-bold text-white">
              Dataset Generation Succeeded
            </h2>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800">
              ID: {schema_id}
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono text-slate-300">
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-cyan-400" />
              <span>{metrics.duration_ms} ms</span>
            </span>
            <span className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-emerald-400" />
              <span>{metrics.total_records.toLocaleString()} records</span>
            </span>
            <span className="flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-amber-400" />
              <span>{metrics.total_entities} entities</span>
            </span>
          </div>
        </div>

        {/* Topological Order Trail */}
        <div className="text-xs font-mono text-slate-400 flex items-center gap-2 flex-wrap">
          <span className="text-slate-500 font-sans">Topological Order:</span>
          {execution_order.map((name, i) => (
            <React.Fragment key={name}>
              <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-emerald-300 font-bold">
                {name}
              </span>
              {i < execution_order.length - 1 && <span className="text-slate-600">➔</span>}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Artifact Download Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        
        {/* PostgreSQL DDL */}
        {artifacts.sql && (
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xl">🐘</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-300">.sql</span>
              </div>
              <h3 className="text-xs font-bold text-white mt-2">PostgreSQL Migration</h3>
              <p className="text-[11px] text-slate-400 mt-1">
                Complete DDL schema with primary/foreign keys and batched INSERT statements.
              </p>
            </div>
            <a
              href={`${baseUrl}${artifacts.sql.download_url}`}
              download
              className="w-full text-xs py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center justify-center gap-2"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .sql Script</span>
            </a>
          </div>
        )}

        {/* Excel Workbook */}
        {artifacts.excel && (
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xl">📊</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-emerald-300">.xlsx</span>
              </div>
              <h3 className="text-xs font-bold text-white mt-2">Excel Workbook</h3>
              <p className="text-[11px] text-slate-400 mt-1">
                Multi-worksheet workbook with each entity organized as a separate tab.
              </p>
            </div>
            <a
              href={`${baseUrl}${artifacts.excel.download_url}`}
              download
              className="w-full text-xs py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center justify-center gap-2"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .xlsx File</span>
            </a>
          </div>
        )}

        {/* CSV Archive */}
        {artifacts.csv && (
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xl">📁</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-amber-300">.zip</span>
              </div>
              <h3 className="text-xs font-bold text-white mt-2">CSV Collection (.zip)</h3>
              <p className="text-[11px] text-slate-400 mt-1">
                Zipped directory containing individual comma-separated files per entity.
              </p>
            </div>
            <a
              href={`${baseUrl}${artifacts.csv.download_url}`}
              download
              className="w-full text-xs py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center justify-center gap-2"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .csv Archive</span>
            </a>
          </div>
        )}

        {/* Parquet Columnar */}
        {artifacts.parquet && (
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xl">📦</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-purple-300">.parquet</span>
              </div>
              <h3 className="text-xs font-bold text-white mt-2">Apache Parquet</h3>
              <p className="text-[11px] text-slate-400 mt-1">
                Columnar analytical files compressed with Snappy, ready for DuckDB or Snowflake.
              </p>
            </div>
            <a
              href={`${baseUrl}${artifacts.parquet.download_url}`}
              download
              className="w-full text-xs py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center justify-center gap-2"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .parquet Archive</span>
            </a>
          </div>
        )}

        {/* JSON Document */}
        {artifacts.json && (
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xl">🏷️</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-yellow-300">.json</span>
              </div>
              <h3 className="text-xs font-bold text-white mt-2">JSON Document Payload</h3>
              <p className="text-[11px] text-slate-400 mt-1">
                Raw structured JSON containing all entity records.
              </p>
            </div>
            <a
              href={`${baseUrl}${artifacts.json.download_url}`}
              download
              className="w-full text-xs py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center justify-center gap-2"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .json File</span>
            </a>
          </div>
        )}

        {/* Dynamic Mock API */}
        {artifacts.api && (
          <div className="p-4 rounded-xl bg-slate-900 border border-cyan-500/40 space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xl">⚡</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300">REST API</span>
              </div>
              <h3 className="text-xs font-bold text-white mt-2">Dynamic Mock REST Endpoints</h3>
              <p className="text-[11px] text-slate-400 mt-1">
                Embedded DuckDB instance mounted with SQL limit/offset pagination.
              </p>
            </div>
            <button
              onClick={() => setActiveTab('api-explorer')}
              className="w-full text-xs py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-semibold transition flex items-center justify-center gap-2"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Open API Explorer</span>
            </button>
          </div>
        )}

      </div>

      {/* SQL Snippet Preview */}
      {artifacts.sql?.preview_snippet && (
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            PostgreSQL Script Preview
          </h3>
          <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800/80 font-mono text-[11px] text-emerald-300 max-h-[300px] overflow-auto whitespace-pre">
            {artifacts.sql.preview_snippet}
          </pre>
        </div>
      )}

    </div>
  );
};
