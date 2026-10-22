import React, { useState } from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { Plus, Trash2, Database, ChevronRight } from 'lucide-react';

export const EntityList: React.FC = () => {
  const {
    entities,
    selectedEntityIndex,
    setSelectedEntityIndex,
    addEntity,
    removeEntity
  } = useSchemaStore();

  const [newEntityName, setNewEntityName] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (newEntityName.trim()) {
      addEntity(newEntityName);
      setNewEntityName('');
      setIsAdding(false);
    }
  };

  return (
    <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Database className="w-3.5 h-3.5 text-emerald-400" />
          <span>Entities ({entities.length})</span>
        </h3>
        <button
          onClick={() => setIsAdding(!isAdding)}
          className="text-xs px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center gap-1"
        >
          <Plus className="w-3 h-3" />
          <span>Entity</span>
        </button>
      </div>

      {isAdding && (
        <form onSubmit={handleAdd} className="space-y-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800">
          <input
            type="text"
            placeholder="Entity name (e.g. invoices)..."
            value={newEntityName}
            onChange={(e) => setNewEntityName(e.target.value)}
            autoFocus
            className="w-full text-xs bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white font-mono placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
          />
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setIsAdding(false)}
              className="text-[11px] px-2 py-0.5 rounded text-slate-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="text-[11px] px-2.5 py-1 rounded bg-emerald-600 text-white font-medium"
            >
              Add
            </button>
          </div>
        </form>
      )}

      {/* Entity Items */}
      <div className="space-y-1.5">
        {entities.map((entity, idx) => {
          const isSelected = idx === selectedEntityIndex;
          return (
            <div
              key={entity.name}
              onClick={() => setSelectedEntityIndex(idx)}
              className={`group cursor-pointer p-2.5 rounded-lg border transition flex items-center justify-between ${
                isSelected
                  ? 'bg-emerald-500/10 border-emerald-500/50 text-white'
                  : 'bg-slate-950/60 border-slate-800/80 text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <div>
                <p className="text-xs font-bold font-mono text-white flex items-center gap-1.5">
                  <span>{entity.name}</span>
                </p>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  {entity.attributes.length} attrs • {entity.record_count.toLocaleString()} records
                </p>
              </div>

              <div className="flex items-center gap-1.5">
                {entities.length > 1 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm(`Delete entity '${entity.name}'?`)) {
                        removeEntity(idx);
                      }
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-950/60 text-slate-500 hover:text-rose-400 transition"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
                <ChevronRight className={`w-3.5 h-3.5 ${isSelected ? 'text-emerald-400' : 'text-slate-600'}`} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
