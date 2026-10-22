import React from 'react';
import { useSchemaStore } from '../store/useSchemaStore';
import { ShieldAlert, Zap } from 'lucide-react';

export const ConsistencyPolicyPanel: React.FC = () => {
  const { policy, setPolicyPreset, updatePolicy } = useSchemaStore();

  return (
    <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
          <span>Consistency & Anomaly Policy</span>
        </h3>

        {/* Quick Presets */}
        <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
          {(['strict', 'mild', 'chaos'] as const).map((preset) => (
            <button
              key={preset}
              onClick={() => setPolicyPreset(preset)}
              className={`px-2.5 py-1 rounded-md font-medium capitalize transition ${
                policy.preset === preset
                  ? 'bg-slate-800 text-amber-300 border border-slate-700'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {preset} {preset === 'strict' ? '(0%)' : preset === 'mild' ? '(5%)' : '(25%)'}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
        
        {/* Orphan FK Rate */}
        <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-300 font-medium">Orphan Foreign Keys</span>
            <span className="font-mono text-amber-400 font-bold">
              {Math.round(policy.orphan_rate * 100)}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={Math.round(policy.orphan_rate * 100)}
            onChange={(e) => updatePolicy({ orphan_rate: parseInt(e.target.value) / 100 })}
            className="w-full accent-amber-500 h-1.5 bg-slate-800 rounded cursor-pointer"
          />
          <p className="text-[10px] text-slate-500">
            Injects dangling IDs to test ETL error handling.
          </p>
        </div>

        {/* Locale Drift Rate */}
        <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-300 font-medium">Locale Drift</span>
            <span className="font-mono text-cyan-400 font-bold">
              {Math.round(policy.locale_drift_rate * 100)}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={Math.round(policy.locale_drift_rate * 100)}
            onChange={(e) => updatePolicy({ locale_drift_rate: parseInt(e.target.value) / 100 })}
            className="w-full accent-cyan-500 h-1.5 bg-slate-800 rounded cursor-pointer"
          />
          <p className="text-[10px] text-slate-500">
            Cross-country attribute mixing rate.
          </p>
        </div>

        {/* Data Noise Rate */}
        <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-300 font-medium">Data Noise Rate</span>
            <span className="font-mono text-purple-400 font-bold">
              {Math.round(policy.noise_rate * 100)}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={Math.round(policy.noise_rate * 100)}
            onChange={(e) => updatePolicy({ noise_rate: parseInt(e.target.value) / 100 })}
            className="w-full accent-purple-500 h-1.5 bg-slate-800 rounded cursor-pointer"
          />
          <p className="text-[10px] text-slate-500">
            Untrimmed spaces, "N/A" sentinels, format bugs.
          </p>
        </div>

      </div>
    </div>
  );
};
