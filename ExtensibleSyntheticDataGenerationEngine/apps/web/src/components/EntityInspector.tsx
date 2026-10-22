import React, { useState } from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { AttributeDefinition, GeneratorType } from '../lib/types';
import { Plus, Trash2, Key, Link2, Settings } from 'lucide-react';

const GENERATOR_TYPES: { type: GeneratorType; label: string; group: string }[] = [
  { type: 'autoincrement', label: 'Autoincrement ID', group: 'Keys' },
  { type: 'uuid', label: 'UUID (v4)', group: 'Keys' },
  { type: 'foreign_key', label: 'Foreign Key ➔', group: 'Keys' },
  { type: 'full_name', label: 'Full Name (Localized)', group: 'Personal' },
  { type: 'first_name', label: 'First Name', group: 'Personal' },
  { type: 'last_name', label: 'Last Name', group: 'Personal' },
  { type: 'email', label: 'Email Address', group: 'Personal' },
  { type: 'phone', label: 'Phone Number', group: 'Personal' },
  { type: 'street_address', label: 'Street Address', group: 'Geographic' },
  { type: 'city', label: 'City', group: 'Geographic' },
  { type: 'country', label: 'Country Name', group: 'Geographic' },
  { type: 'date_time', label: 'Date / Timestamp', group: 'Temporal' },
  { type: 'numeric_range', label: 'Numeric Range (Int/Float)', group: 'Values' },
  { type: 'categorical', label: 'Categorical Choice', group: 'Values' },
  { type: 'boolean', label: 'Boolean Flag', group: 'Values' },
  { type: 'text', label: 'Paragraph / Text', group: 'Content' }
];

export const EntityInspector: React.FC = () => {
  const {
    entities,
    selectedEntityIndex,
    setEntityRecordCount,
    addAttribute,
    removeAttribute,
    updateAttribute
  } = useSchemaStore();

  const currentEntity = entities[selectedEntityIndex] || entities[0];

  const [isAddingAttr, setIsAddingAttr] = useState(false);
  const [newAttrName, setNewAttrName] = useState('');
  const [newAttrType, setNewAttrType] = useState<GeneratorType>('text');

  // Build list of valid foreign key targets from all entities' primary keys
  const availableFkTargets: string[] = [];
  entities.forEach((ent) => {
    ent.attributes.forEach((attr) => {
      if (attr.is_primary_key || attr.name === 'id') {
        availableFkTargets.push(`${ent.name}.${attr.name}`);
      }
    });
  });

  const handleCreateAttribute = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAttrName.trim()) return;

    const newAttr: AttributeDefinition = {
      name: newAttrName.trim(),
      type: newAttrType,
      is_primary_key: false,
      nullable: false,
      fk_target: newAttrType === 'foreign_key' ? availableFkTargets[0] : undefined
    };

    addAttribute(selectedEntityIndex, newAttr);
    setNewAttrName('');
    setIsAddingAttr(false);
  };

  if (!currentEntity) {
    return <div className="p-8 text-center text-slate-500">Select an entity to view details.</div>;
  }

  return (
    <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-5">
      
      {/* Entity Header & Record Volume Control */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-base font-bold text-white font-mono flex items-center gap-2">
            <span>Entity:</span>
            <span className="text-emerald-400">{currentEntity.name}</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Configure schema attributes, relational references, and generation volume.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
            <label className="text-xs text-slate-400 font-medium">Record Count:</label>
            <input
              type="number"
              min={1}
              max={1000000}
              value={currentEntity.record_count}
              onChange={(e) => setEntityRecordCount(selectedEntityIndex, parseInt(e.target.value) || 1)}
              className="w-24 px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-xs font-mono text-white text-right focus:outline-none focus:border-emerald-500"
            />
          </div>

          <button
            onClick={() => setIsAddingAttr(!isAddingAttr)}
            className="text-xs px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center gap-1.5 shadow"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Attribute</span>
          </button>
        </div>
      </div>

      {/* Inline Add Attribute Bar */}
      {isAddingAttr && (
        <form onSubmit={handleCreateAttribute} className="p-3 rounded-lg bg-slate-950 border border-emerald-500/40 flex flex-wrap items-center gap-3">
          <input
            type="text"
            placeholder="Attribute name (e.g. status)..."
            value={newAttrName}
            onChange={(e) => setNewAttrName(e.target.value)}
            autoFocus
            className="text-xs bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-white font-mono placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 min-w-[200px]"
          />

          <select
            value={newAttrType}
            onChange={(e) => setNewAttrType(e.target.value as GeneratorType)}
            className="text-xs bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200 focus:outline-none"
          >
            {GENERATOR_TYPES.map((g) => (
              <option key={g.type} value={g.type}>
                {g.label}
              </option>
            ))}
          </select>

          <div className="flex items-center gap-2 ml-auto">
            <button
              type="button"
              onClick={() => setIsAddingAttr(false)}
              className="text-xs px-2.5 py-1 text-slate-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="text-xs px-3 py-1 rounded bg-emerald-600 text-white font-medium hover:bg-emerald-500"
            >
              Add to Entity
            </button>
          </div>
        </form>
      )}

      {/* Attributes Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60 font-medium">
              <th className="py-2.5 px-3">Attribute</th>
              <th className="py-2.5 px-3">Generator Type</th>
              <th className="py-2.5 px-3 text-center">Primary Key</th>
              <th className="py-2.5 px-3 text-center">Nullable</th>
              <th className="py-2.5 px-3">Relationship / Target</th>
              <th className="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono">
            {currentEntity.attributes.map((attr, attrIdx) => (
              <tr key={attr.name} className="hover:bg-slate-950/40 transition">
                
                {/* Attribute Name */}
                <td className="py-2.5 px-3 font-semibold text-white">
                  {attr.name}
                </td>

                {/* Generator Type Selector */}
                <td className="py-2.5 px-3">
                  <select
                    value={attr.type}
                    onChange={(e) => {
                      const type = e.target.value as GeneratorType;
                      const updates: Partial<AttributeDefinition> = { type };
                      if (type === 'foreign_key' && !attr.fk_target && availableFkTargets.length > 0) {
                        updates.fk_target = availableFkTargets[0];
                      }
                      updateAttribute(selectedEntityIndex, attrIdx, updates);
                    }}
                    className="text-[11px] bg-slate-950 border border-slate-700 rounded px-2 py-1 text-cyan-300 focus:outline-none focus:border-cyan-500"
                  >
                    {GENERATOR_TYPES.map((g) => (
                      <option key={g.type} value={g.type}>
                        {g.label}
                      </option>
                    ))}
                  </select>
                </td>

                {/* Primary Key Checkbox */}
                <td className="py-2.5 px-3 text-center">
                  <button
                    onClick={() =>
                      updateAttribute(selectedEntityIndex, attrIdx, {
                        is_primary_key: !attr.is_primary_key
                      })
                    }
                    className={`p-1 rounded transition ${
                      attr.is_primary_key
                        ? 'text-amber-400 bg-amber-500/10 border border-amber-500/30'
                        : 'text-slate-600 hover:text-slate-400'
                    }`}
                  >
                    <Key className="w-3.5 h-3.5 inline" />
                  </button>
                </td>

                {/* Nullable Checkbox */}
                <td className="py-2.5 px-3 text-center">
                  <input
                    type="checkbox"
                    checked={attr.nullable}
                    onChange={(e) =>
                      updateAttribute(selectedEntityIndex, attrIdx, {
                        nullable: e.target.checked
                      })
                    }
                    className="accent-emerald-500 cursor-pointer rounded"
                  />
                </td>

                {/* Foreign Key Target Dropdown */}
                <td className="py-2.5 px-3">
                  {attr.type === 'foreign_key' ? (
                    <div className="flex items-center gap-1.5">
                      <Link2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      <select
                        value={attr.fk_target || ''}
                        onChange={(e) =>
                          updateAttribute(selectedEntityIndex, attrIdx, {
                            fk_target: e.target.value
                          })
                        }
                        className="text-[11px] bg-slate-950 border border-slate-700 rounded px-2 py-1 text-emerald-300 font-semibold focus:outline-none focus:border-emerald-500"
                      >
                        {availableFkTargets.map((target) => (
                          <option key={target} value={target}>
                            ➔ {target}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <span className="text-slate-600 font-sans text-[11px]">—</span>
                  )}
                </td>

                {/* Actions */}
                <td className="py-2.5 px-3 text-right">
                  {currentEntity.attributes.length > 1 && (
                    <button
                      onClick={() => removeAttribute(selectedEntityIndex, attrIdx)}
                      className="p-1 rounded hover:bg-rose-950/60 text-slate-500 hover:text-rose-400 transition"
                      title="Delete attribute"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </td>

              </tr>
            ))}
          </tbody>
        </table>
      </div>

    </div>
  );
};
