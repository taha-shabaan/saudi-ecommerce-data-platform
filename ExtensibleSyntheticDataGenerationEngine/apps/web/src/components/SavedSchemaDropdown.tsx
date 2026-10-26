'use client';

import React, { useEffect, useState } from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { Save, ChevronDown, Trash2, Check, Clock } from 'lucide-react';

const ORIGIN_LABELS: Record<string, string> = {
  dbml_import: 'DBML',
  template: 'Template',
  canvas: 'Canvas'
};

const originBadge = (origin: string) => {
  switch (origin) {
    case 'dbml_import':
      return 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300';
    case 'template':
      return 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300';
    default:
      return 'bg-slate-500/15 border-slate-500/40 text-slate-300';
  }
};

const shortDate = (iso: string) => {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  });
};

export const SavedSchemaDropdown: React.FC = () => {
  const {
    savedSchemas,
    savedSchemasLoading,
    isDirty,
    fetchSavedSchemas,
    loadSavedSchema,
    deleteSavedSchema
  } = useSchemaStore();

  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState<string | null>(null); // context menu state per row (trash confirm)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  useEffect(() => {
    fetchSavedSchemas();
  }, [fetchSavedSchemas]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('[data-saved-schema-root]')) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setConfirmDelete(null);
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  const handleLoad = async (name: string) => {
    if (isDirty && !window.confirm('The canvas has unsaved changes. Load the saved schema anyway?')) {
      return;
    }
    await loadSavedSchema(name);
    setOpen(false);
  };

  const handleDelete = async (name: string) => {
    if (confirmDelete !== name) {
      setConfirmDelete(name);
      return;
    }
    await deleteSavedSchema(name);
    setConfirmDelete(null);
  };

  return (
    <div data-saved-schema-root className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`text-xs px-3 py-1.5 rounded-md border flex items-center gap-1.5 font-medium transition ${
          open
            ? 'bg-slate-800 border-cyan-500/60 text-cyan-300'
            : 'bg-slate-800 border-slate-700 text-slate-200 hover:border-slate-600'
        }`}
        title="Schemas stored in the registry — retrieve or delete previously saved configurations"
      >
        <Save className="w-3.5 h-3.5 text-cyan-400" />
        <span>My Schemas</span>
        {savedSchemas.length > 0 && (
          <span className="px-1.5 rounded-full bg-cyan-500/20 border border-cyan-500/40 text-[10px] text-cyan-300 font-mono">
            {savedSchemas.length}
          </span>
        )}
        <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 rounded-xl bg-slate-900 border border-slate-700 shadow-2xl shadow-black/60 overflow-hidden z-50">
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between">
            <span>Saved Schema Registry</span>
            <span className="flex items-center gap-1 normal-case text-slate-600">
              <Clock className="w-3 h-3" /> auto-saved on import
            </span>
          </div>

          {savedSchemasLoading ? (
            <div className="px-3 py-6 text-center text-[11px] text-slate-500">Loading registry…</div>
          ) : savedSchemas.length === 0 ? (
            <div className="px-3 py-6 text-center text-[11px] text-slate-500">
              No saved schemas yet.
              <br />
              Import a DBML file or load a template to save one automatically.
            </div>
          ) : (
            <ul className="max-h-72 overflow-y-auto py-1">
              {savedSchemas.map((item) => (
                <li key={item.name} className="group relative flex items-stretch">
                  <button
                    onClick={() => handleLoad(item.name)}
                    className="flex-1 min-w-0 flex items-center gap-2.5 px-3 py-2 text-left hover:bg-slate-800 transition"
                  >
                    <span className={`shrink-0 text-[9px] font-mono px-1.5 py-0.5 rounded border ${originBadge(item.origin)}`}>
                      {ORIGIN_LABELS[item.origin] ?? item.origin}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="block text-xs font-medium text-slate-100 truncate">
                        {item.name}
                      </span>
                      <span className="block text-[10px] text-slate-500">
                        {item.entity_count} entities • saved {shortDate(item.updated_at)}
                      </span>
                    </span>
                  </button>
                  <button
                    onClick={() => handleDelete(item.name)}
                    className={`shrink-0 px-2.5 flex items-center transition ${
                      confirmDelete === item.name
                        ? 'text-rose-300 bg-rose-500/10'
                        : 'text-slate-600 opacity-0 group-hover:opacity-100 hover:text-rose-300'
                    }`}
                    title={confirmDelete === item.name ? 'Click again to confirm delete' : 'Delete saved schema'}
                  >
                    {confirmDelete === item.name
                      ? <Check className="w-3.5 h-3.5" />
                      : <Trash2 className="w-3.5 h-3.5" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};
