import React from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { AVAILABLE_COUNTRIES } from '../lib/templates';
import { Globe } from 'lucide-react';

export const LocalesSelector: React.FC = () => {
  const { activeLocales, toggleLocale } = useSchemaStore();

  return (
    <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Globe className="w-3.5 h-3.5 text-emerald-400" />
          <span>Target Locales (Multi-Country)</span>
        </h3>
        <span className="text-[10px] text-emerald-400 font-mono">
          {activeLocales.length} Selected
        </span>
      </div>
      <p className="text-xs text-slate-500">
        Row-level locale binding ensures culturally coherent names, phones, and addresses.
      </p>

      <div className="flex flex-wrap gap-2 pt-1">
        {AVAILABLE_COUNTRIES.map((item) => {
          const isActive = activeLocales.includes(item.code);
          return (
            <button
              key={item.code}
              onClick={() => toggleLocale(item.code)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1.5 ${
                isActive
                  ? 'bg-emerald-500/15 border-emerald-500/50 text-emerald-300'
                  : 'bg-slate-950 border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-700'
              }`}
            >
              <span>{item.flag}</span>
              <span>{item.country}</span>
              <span className="text-[10px] font-mono opacity-60">({item.code})</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
