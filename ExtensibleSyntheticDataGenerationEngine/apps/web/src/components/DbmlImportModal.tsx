'use client';

import React, { useRef, useState } from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { EntityDefinition } from '../lib/types';
import { Upload, X, FileCode2 } from 'lucide-react';

export const DbmlImportModal: React.FC = () => {
  const { loadDbmlSchema, saveSchema } = useSchemaStore();
  const [open, setOpen] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [source, setSource] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setOpen(false);
    setProjectName('');
    setSource('');
    setError(null);
    setWarnings([]);
    setFileName(null);
    setDragging(false);
  };

  const readFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      setSource(String(reader.result || ''));
      setFileName(file.name);
      setError(null);
      if (!projectName) {
        const base = file.name.replace(/\.(dbml|txt|sql)$/i, '');
        setProjectName(base.replace(/[-\s]+/g, '_'));
      }
    };
    reader.readAsText(file);
  };

  const canImport = !busy && !!source.trim();
  const doImport = async () => {
    if (!source.trim()) return;
    setBusy(true);
    setError(null);
    setWarnings([]);
    try {
      const name = projectName.trim() || (fileName?.replace(/\.(dbml|txt|sql)$/i, '').replace(/[-\s]+/g, '_')) || 'imported_schema';
      const res = await fetch('http://localhost:8000/api/v1/schemas/import-dbml', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, source })
      });
      const body = await res.json();
      if (!res.ok) {
        const detail = body.detail;
        if (detail && typeof detail === 'object' && Array.isArray(detail.diagnostics)) {
          const lines = detail.diagnostics
            .map((d: { line: number; message: string }) => `line ${d.line}: ${d.message}`)
            .join('\n');
          throw new Error(`${detail.message}\n${lines}`);
        }
        throw new Error(typeof detail === 'object' ? detail.message : String(detail));
      }
      loadDbmlSchema(body.name, body.entities as EntityDefinition[], source);
      // Auto-save the imported snapshot (overwrite confirmed via store dialog on name clash)
      const outcome = await saveSchema({ name: body.name, origin: 'dbml_import', dbmlSource: source });
      if (outcome === 'failed') {
        window.alert('Import succeeded, but auto-saving to the Schema Registry failed.');
      }
      setWarnings(body.warnings || []);
      if (!(body.warnings || []).length) reset();
    } catch (err: any) {
      setError(err.message || 'DBML import failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-xs px-3 py-1.5 rounded-md bg-slate-800 border border-slate-700 text-slate-200 hover:border-cyan-500/60 hover:text-cyan-300 transition flex items-center gap-1.5"
        title="Upload a DBDiagram.io (DBML) schema"
      >
        <Upload className="w-3.5 h-3.5" />
        <span>Import DBML...</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl shadow-2xl">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <FileCode2 className="w-4 h-4 text-cyan-400" />
                Import DBDiagram.io Schema (DBML)
              </div>
              <button onClick={reset} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-5 py-4 space-y-3.5">
              <div>
                <label className="text-[11px] uppercase tracking-wide text-slate-400 font-medium">
                  Project Name
                </label>
                <input
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="auto-filled from file name (e.g. ecommerce_core)"
                  className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-md px-3 py-2 text-xs text-slate-100 focus:border-cyan-500/60 outline-none"
                />
              </div>

              <div>
                <label className="text-[11px] uppercase tracking-wide text-slate-400 font-medium">
                  Schema Syntax (DBML)
                </label>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".dbml,.txt,.sql"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) readFile(f);
                    e.target.value = '';
                  }}
                />
                {(() => (
                  <div
                    onClick={() => fileRef.current?.click()}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragging(false);
                      const f = e.dataTransfer.files?.[0];
                      if (f) readFile(f);
                    }}
                    className={`mt-1 w-full flex flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed py-4 transition cursor-pointer ${
                      dragging
                        ? 'border-cyan-400 bg-cyan-500/10'
                        : 'border-slate-700 bg-slate-950 hover:border-cyan-500/60'
                    }`}
                  >
                    <Upload className={`w-5 h-5 ${dragging ? 'text-cyan-300' : 'text-slate-500'}`} />
                    <p className="text-[11px] text-slate-300 font-medium">
                      {fileName ? fileName : 'Drop a .dbml file here or click to upload'}
                    </p>
                    <p className="text-[10px] text-slate-500">
                      or paste DBML below (Table / Ref / enum syntax)
                    </p>
                  </div>
                ))()}
                <textarea
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  rows={10}
                  spellCheck={false}
                  placeholder={'Table users {\n  id int [pk]\n  email varchar\n}\n\nTable orders {\n  id int [pk]\n  customer_id int\n}\n\nRef: orders.customer_id > users.id'}
                  className="mt-2 w-full bg-slate-950 border border-slate-700 rounded-md px-3 py-2 text-[11px] font-mono text-slate-100 focus:border-cyan-500/60 outline-none"
                />
              </div>

              {error && (
                <pre className="text-[11px] whitespace-pre-wrap bg-rose-950/40 border border-rose-800/60 text-rose-300 rounded-md px-3 py-2">
                  {error}
                </pre>
              )}

              {warnings.length > 0 && !error && (
                <ul className="text-[11px] bg-amber-950/30 border border-amber-800/50 text-amber-300 rounded-md px-3 py-2 space-y-1">
                  {warnings.map((w, i) => (
                    <li key={i}>⚠ {w}</li>
                  ))}
                </ul>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t border-slate-800">
              <button onClick={reset} className="text-xs px-3 py-1.5 rounded-md bg-slate-800 border border-slate-700 text-slate-300 hover:text-white">
                Cancel
              </button>
              <button
                onClick={doImport}
                disabled={!canImport}
                className={`text-xs px-4 py-1.5 rounded-md font-semibold transition ${
                  canImport
                    ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                    : 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                }`}
              >
                {busy ? 'Importing…' : 'Import Schema'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
