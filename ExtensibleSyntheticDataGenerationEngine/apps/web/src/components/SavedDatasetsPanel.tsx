'use client';

import React, { useEffect, useState } from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { History, Download, Database } from 'lucide-react';

interface SavedDatasetMeta {
  dataset_id: string;
  created_at: string;
  row_counts: Record<string, number>;
  metrics?: { total_records?: number };
}

const EXPORT_TYPES: { key: string; label: string }[] = [
  { key: 'sql', label: 'SQL' },
  { key: 'excel', label: 'Excel' },
  { key: 'csv', label: 'CSV' },
  { key: 'parquet', label: 'Parquet' },
  { key: 'json', label: 'JSON' },
];

export const SavedDatasetsPanel: React.FC = () => {
  const { generationResult } = useSchemaStore();
  const [datasets, setDatasets] = useState<SavedDatasetMeta[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const schemaId = generationResult?.schema_id;

  useEffect(() => {
    if (!schemaId) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${baseUrl}/api/v1/datasets/${encodeURIComponent(schemaId)}`);
        if (!res.ok) throw new Error('list failed');
        const data = await res.json();
        if (!cancelled) {
          setDatasets(data.datasets);
          setLoadFailed(false);
        }
      } catch {
        if (!cancelled) setLoadFailed(true);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schemaId]);

  if (!schemaId) return null;

  const downloadHref = (datasetId: string, type: string) =>
    `${baseUrl}/api/v1/download/${schemaId}/${type}?dataset_id=${datasetId}`;

  return (
    <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        <History className="w-4 h-4 text-cyan-400" />
        <h3 className="text-xs font-bold uppercase tracking-wider text-white">
          Saved Datasets
        </h3>
        <span className="text-[10px] font-mono text-slate-500">
          persisted per generation · survives restarts
        </span>
      </div>

      {loadFailed && (
        <p className="text-xs text-rose-400 font-mono">
          Could not load saved datasets for schema {schemaId}.
        </p>
      )}

      {datasets === null && !loadFailed && (
        <p className="text-xs text-slate-500 font-mono">Loading saved datasets…</p>
      )}

      {datasets !== null && datasets.length === 0 && (
        <p className="text-xs text-slate-500 font-mono">No saved datasets for this schema yet.</p>
      )}

      <div className="space-y-3">
        {(datasets || []).map((ds, index) => (
          <div
            key={ds.dataset_id}
            className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 space-y-2"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs">
                <Database className="w-3.5 h-3.5 text-emerald-400" />
                <span className="font-mono text-emerald-300 font-semibold">
                  {ds.dataset_id}
                </span>
                {index === 0 && datasets !== null && datasets.length > 1 && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300">
                    latest
                  </span>
                )}
              </div>
              <span className="text-[11px] font-mono text-slate-400">
                {new Date(ds.created_at).toLocaleString()} ·{' '}
                {Object.values(ds.row_counts).reduce((a, b) => a + b, 0)} rows
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {EXPORT_TYPES.map(({ key, label }) => (
                <a
                  key={key}
                  href={downloadHref(ds.dataset_id, key)}
                  download
                  className="text-[11px] px-2.5 py-1.5 rounded bg-slate-900 hover:bg-emerald-900/60 border border-slate-800 text-slate-200 hover:text-white font-medium transition flex items-center gap-1.5"
                >
                  <Download className="w-3 h-3" />
                  {label}
                </a>
              ))}
              <a
                href={`${baseUrl}/api/v1/mock/${schemaId}`}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] px-2.5 py-1.5 rounded bg-cyan-600/20 hover:bg-cyan-600/40 border border-cyan-500/40 text-cyan-200 font-medium transition flex items-center gap-1.5"
              >
                <Download className="w-3 h-3" />
                Mock API
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
