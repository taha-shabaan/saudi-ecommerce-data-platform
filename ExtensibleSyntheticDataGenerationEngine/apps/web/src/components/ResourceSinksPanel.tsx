import React from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { ExportSinksConfig } from '../lib/types';
import { DownloadCloud } from 'lucide-react';

const SINKS = [
  { id: 'parquet' as keyof ExportSinksConfig, label: 'Apache Parquet', icon: '📦', ext: '.parquet', desc: 'Columnar Snappy storage' },
  { id: 'json' as keyof ExportSinksConfig, label: 'JSON Documents', icon: '🏷️', ext: '.json', desc: 'Structured payloads' },
  { id: 'postgres' as keyof ExportSinksConfig, label: 'PostgreSQL', icon: '🐘', ext: '.sql', desc: 'DDL & batched INSERTs' },
  { id: 'excel' as keyof ExportSinksConfig, label: 'Excel Workbook', icon: '📊', ext: '.xlsx', desc: 'Multi-tab openpyxl sheets' },
  { id: 'csv' as keyof ExportSinksConfig, label: 'CSV Archive', icon: '📁', ext: '.zip', desc: 'Zipped per-entity files' },
  { id: 'api' as keyof ExportSinksConfig, label: 'Mock REST API', icon: '⚡', ext: 'REST', desc: 'DuckDB paginated routes' },
];

export const ResourceSinksPanel: React.FC = () => {
  const { sinks, toggleSink } = useSchemaStore();

  return (
    <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <DownloadCloud className="w-3.5 h-3.5 text-cyan-400" />
          <span>Target Resource Sinks</span>
        </h3>
        <span className="text-[10px] text-slate-500 font-mono">
          {Object.values(sinks).filter((v) => typeof v === 'boolean' && v).length} Enabled
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
        {SINKS.map((sink) => {
          const isEnabled = Boolean(sinks[sink.id]);
          return (
            <div
              key={sink.id}
              onClick={() => toggleSink(sink.id)}
              className={`cursor-pointer p-3 rounded-xl border transition flex flex-col justify-between ${
                isEnabled
                  ? 'bg-emerald-500/10 border-emerald-500/50 text-white shadow-sm'
                  : 'bg-slate-950/60 border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-lg">{sink.icon}</span>
                <span
                  className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                    isEnabled ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-800 text-slate-500'
                  }`}
                >
                  {sink.ext}
                </span>
              </div>
              <div className="mt-2">
                <p className={`text-xs font-bold leading-tight ${isEnabled ? 'text-white' : 'text-slate-400'}`}>
                  {sink.label}
                </p>
                <p className="text-[9px] text-slate-500 mt-0.5 line-clamp-1">{sink.desc}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
