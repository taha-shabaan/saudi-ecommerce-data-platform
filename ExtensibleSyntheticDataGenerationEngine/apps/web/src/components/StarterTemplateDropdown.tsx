'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { STARTER_TEMPLATES } from '../lib/templates';
import { ChevronDown, LayoutTemplate } from 'lucide-react';

export const StarterTemplateDropdown: React.FC = () => {
  const { loadTemplate, savedSchemas, saveSchema } = useSchemaStore();
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  const pick = (id: string) => {
    loadTemplate(id);
    // Auto-save the unpolluted template snapshot (re-saving the same template
    // silently overwrites; anything else with the same name asks first)
    const existing = savedSchemas.find((s) => s.name === id);
    saveSchema({
      name: id,
      origin: 'template',
      dbmlSource: null,
      silentOverwrite: !existing || existing.origin === 'template'
    }).then((outcome) => {
      if (outcome === 'failed') {
        window.alert('Template loaded, but auto-saving to the Schema Registry failed.');
      }
    });
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => {
          setOpen((v) => !v);
          setHighlighted(-1);
        }}
        className={`text-xs px-3 py-1.5 rounded-md border flex items-center gap-1.5 font-medium transition ${
          open
            ? 'bg-slate-800 border-cyan-500/60 text-cyan-300'
            : 'bg-slate-800 border-slate-700 text-slate-200 hover:border-slate-600'
        }`}
      >
        <LayoutTemplate className="w-3.5 h-3.5 text-emerald-400" />
        <span>Load Starter Template</span>
        <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-72 rounded-xl bg-slate-900 border border-slate-700 shadow-2xl shadow-black/60 overflow-hidden z-50">
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-800 bg-slate-950/60">
            Starter Schemas
          </div>
          <ul className="max-h-64 overflow-y-auto py-1">
            {STARTER_TEMPLATES.map((tmpl, i) => (
              <li key={tmpl.id}>
                <button
                  onMouseEnter={() => setHighlighted(i)}
                  onClick={() => pick(tmpl.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition ${
                    highlighted === i ? 'bg-slate-800' : ''
                  }`}
                >
                  <span className="text-base leading-none">{tmpl.icon}</span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-xs font-medium text-slate-100 truncate">
                      {tmpl.name}
                    </span>
                    {tmpl.description && (
                      <span className="block text-[10px] text-slate-500 truncate">
                        {tmpl.description}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
