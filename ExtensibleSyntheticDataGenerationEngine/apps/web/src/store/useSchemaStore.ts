import { create } from 'zustand';
import {
  EntityDefinition,
  AttributeDefinition,
  ConsistencyPolicy,
  ExportSinksConfig,
  GenerateRequest,
  GenerateResponse
} from '../lib/types';
import { STARTER_TEMPLATES } from '../lib/templates';

const API_BASE = 'http://localhost:8000';

export interface SavedSchemaMeta {
  name: string;
  origin: 'dbml_import' | 'template' | 'canvas';
  entity_count: number;
  created_at: string;
  updated_at: string;
}

/** Result of a Saved Schema save attempt. */
export type SaveSchemaOutcome = 'saved' | 'cancelled' | 'failed';

export interface SaveSchemaOptions {
  name?: string;
  origin?: SavedSchemaMeta['origin'];
  /** Provenance for DBML imports; omit to fall back to the canvas's current source, pass null to clear it. */
  dbmlSource?: string | null;
  /** Skip the overwrite confirmation (used by template→template auto-save). */
  silentOverwrite?: boolean;
}

/** Canonical Saved Schema payload — key order is stable for round-trip dirty checks. */
const buildSnapshot = (state: {
  schemaName: string;
  activeLocales: string[];
  entities: EntityDefinition[];
  policy: ConsistencyPolicy;
  sinks: ExportSinksConfig;
}) => ({
  name: state.schemaName,
  locales: state.activeLocales,
  entities: state.entities,
  policy: state.policy,
  sinks: state.sinks
});


interface DAGValidationResult {
  isValid: boolean;
  order: string[];
  cycleNodes?: string[];
  errorMessage?: string;
}

interface SchemaStoreState {
  entities: EntityDefinition[];
  activeLocales: string[];
  selectedEntityIndex: number;
  policy: ConsistencyPolicy;
  sinks: ExportSinksConfig;
  isGenerating: boolean;
  error: string | null;
  generationResult: GenerateResponse | null;
  activeTab: 'builder' | 'results' | 'api-explorer';
  schemaName: string;

  // Saved Schema Registry (GLOSSARY.md: Schema Registry)
  savedSchemas: SavedSchemaMeta[];
  savedSchemasLoading: boolean;
  isDirty: boolean;
  /** DBML provenance retained from the latest import so later saves keep it. */
  dbmlSource: string | null;

  // Actions
  setSchemaName: (name: string) => void;
  loadDbmlSchema: (name: string, entities: EntityDefinition[], dbmlSource?: string | null) => void;
  setSelectedEntityIndex: (index: number) => void;
  setActiveTab: (tab: 'builder' | 'results' | 'api-explorer') => void;
  addEntity: (name: string, recordCount?: number) => void;
  removeEntity: (index: number) => void;
  setEntityRecordCount: (index: number, count: number) => void;
  addAttribute: (entityIndex: number, attribute: AttributeDefinition) => void;
  removeAttribute: (entityIndex: number, attrIndex: number) => void;
  updateAttribute: (entityIndex: number, attrIndex: number, updates: Partial<AttributeDefinition>) => void;
  toggleLocale: (locale: string) => void;
  setPolicyPreset: (preset: 'strict' | 'mild' | 'chaos') => void;
  updatePolicy: (updates: Partial<ConsistencyPolicy>) => void;
  toggleSink: (sinkKey: keyof ExportSinksConfig) => void;
  loadTemplate: (templateId: string) => void;
  validateDAG: () => DAGValidationResult;
  generateData: () => Promise<void>;

  fetchSavedSchemas: () => Promise<void>;
  saveSchema: (options?: SaveSchemaOptions) => Promise<SaveSchemaOutcome>;
  loadSavedSchema: (name: string) => Promise<boolean>;
  deleteSavedSchema: (name: string) => Promise<boolean>;
}

export const useSchemaStore = create<SchemaStoreState>((set, get) => ({
  entities: STARTER_TEMPLATES[0].entities,
  activeLocales: ['ar_EG', 'en_US', 'de_DE'],
  selectedEntityIndex: 0,
  policy: {
    preset: 'strict',
    orphan_rate: 0.0,
    locale_drift_rate: 0.0,
    noise_rate: 0.0,
    duplicate_rate: 0.0
  },
  sinks: {
    postgres: true,
    excel: true,
    csv: true,
    parquet: true,
    json: true,
    api: true,
    api_route_prefix: '/api/v1/mock'
  },
  isGenerating: false,
  error: null,
  generationResult: null,
  activeTab: 'builder',
  schemaName: 'Synthetic Dataset',

  savedSchemas: [],
  savedSchemasLoading: false,
  isDirty: false,
  dbmlSource: null,

  setSelectedEntityIndex: (index) => set({ selectedEntityIndex: index }),
  setActiveTab: (tab) => set({ activeTab: tab }),

  setSchemaName: (name) => set({ schemaName: name, isDirty: true }),

  loadDbmlSchema: (name, entities, dbmlSource = null) => {
    set({
      entities: JSON.parse(JSON.stringify(entities)),
      schemaName: name,
      selectedEntityIndex: 0,
      generationResult: null,
      error: null,
      isDirty: true,
      dbmlSource
    });
  },

  addEntity: (name, recordCount = 10) => {
    const cleanName = name.trim().toLowerCase().replace(/\s+/g, '_');
    if (!cleanName) return;

    set((state) => {
      if (state.entities.some((e) => e.name === cleanName)) return state;
      const newEntity: EntityDefinition = {
        name: cleanName,
        record_count: recordCount,
        attributes: [
          { name: 'id', type: 'autoincrement', is_primary_key: true, nullable: false }
        ]
      };
      return {
        entities: [...state.entities, newEntity],
        selectedEntityIndex: state.entities.length,
        isDirty: true
      };
    });
  },

  removeEntity: (index) => {
    set((state) => {
      const removedEntity = state.entities[index];
      const updatedEntities = state.entities.filter((_, i) => i !== index);

      // Clean up foreign keys that pointed to the removed entity
        const sanitized = updatedEntities.map((ent) => ({
          ...ent,
          attributes: ent.attributes.filter(
            (attr) => !attr.fk_target || !attr.fk_target.startsWith(`${removedEntity.name}.`)
          )
        }));

        const newIndex = Math.max(0, Math.min(index, sanitized.length - 1));
        return { entities: sanitized, selectedEntityIndex: newIndex, isDirty: true };
    });
  },

  setEntityRecordCount: (index, count) => {
    set((state) => {
      const entities = [...state.entities];
      if (entities[index]) {
        entities[index] = { ...entities[index], record_count: Math.max(1, count) };
      }
      return { entities, isDirty: true };
    });
  },

  addAttribute: (entityIndex, attribute) => {
    set((state) => {
      const entities = [...state.entities];
      const entity = entities[entityIndex];
      if (!entity) return state;

      // Ensure attribute name is unique within entity
      const cleanName = attribute.name.trim().toLowerCase().replace(/\s+/g, '_');
      if (entity.attributes.some((a) => a.name === cleanName)) return state;

      entities[entityIndex] = {
        ...entity,
        attributes: [...entity.attributes, { ...attribute, name: cleanName }]
      };
      return { entities, isDirty: true };
    });
  },

  removeAttribute: (entityIndex, attrIndex) => {
    set((state) => {
      const entities = [...state.entities];
      const entity = entities[entityIndex];
      if (!entity) return state;

      entities[entityIndex] = {
        ...entity,
        attributes: entity.attributes.filter((_, idx) => idx !== attrIndex)
      };
      return { entities, isDirty: true };
    });
  },

  updateAttribute: (entityIndex, attrIndex, updates) => {
    set((state) => {
      const entities = [...state.entities];
      const entity = entities[entityIndex];
      if (!entity || !entity.attributes[attrIndex]) return state;

      const attrs = [...entity.attributes];
        attrs[attrIndex] = { ...attrs[attrIndex], ...updates };
        entities[entityIndex] = { ...entity, attributes: attrs };
        return { entities, isDirty: true };
    });
  },

  toggleLocale: (locale) => {
    set((state) => {
      const exists = state.activeLocales.includes(locale);
      if (exists) {
        if (state.activeLocales.length === 1) return state; // Keep at least one
        return { activeLocales: state.activeLocales.filter((l) => l !== locale), isDirty: true };
      }
      return { activeLocales: [...state.activeLocales, locale], isDirty: true };
    });
  },

  setPolicyPreset: (preset) => {
    set({
      policy: {
        preset,
        orphan_rate: preset === 'strict' ? 0.0 : preset === 'mild' ? 0.05 : 0.25,
        locale_drift_rate: preset === 'strict' ? 0.0 : preset === 'mild' ? 0.10 : 0.40,
        noise_rate: preset === 'strict' ? 0.0 : preset === 'mild' ? 0.05 : 0.25,
        duplicate_rate: preset === 'strict' ? 0.0 : preset === 'mild' ? 0.02 : 0.15
      },
      isDirty: true
    });
  },

  updatePolicy: (updates) => {
    set((state) => ({
      policy: { ...state.policy, ...updates },
      isDirty: true
    }));
  },

  toggleSink: (sinkKey) => {
    set((state) => {
      if (typeof state.sinks[sinkKey] === 'boolean') {
        return {
          sinks: {
            ...state.sinks,
            [sinkKey]: !state.sinks[sinkKey]
          },
          isDirty: true
        };
      }
      return state;
    });
  },

  loadTemplate: (templateId) => {
    const tmpl = STARTER_TEMPLATES.find((t) => t.id === templateId);
    if (tmpl) {
      set({
        entities: JSON.parse(JSON.stringify(tmpl.entities)),
        schemaName: tmpl.id,
        selectedEntityIndex: 0,
        generationResult: null,
        error: null,
        isDirty: true
      });
    }
  },

  validateDAG: () => {
    const { entities } = get();
    const entityNames = entities.map((e) => e.name);
    const adj: Record<string, string[]> = {};
    const inDegree: Record<string, number> = {};

    entityNames.forEach((name) => {
      adj[name] = [];
      inDegree[name] = 0;
    });

    entities.forEach((entity) => {
      entity.attributes.forEach((attr) => {
        if (attr.type === 'foreign_key' && attr.fk_target) {
          const [parent] = attr.fk_target.split('.');
          if (parent && parent !== entity.name && entityNames.includes(parent)) {
            if (!adj[parent].includes(entity.name)) {
              adj[parent].push(entity.name);
              inDegree[entity.name] = (inDegree[entity.name] || 0) + 1;
            }
          }
        }
      });
    });

    const queue = entityNames.filter((name) => inDegree[name] === 0);
    const order: string[] = [];

    while (queue.length > 0) {
      const current = queue.shift()!;
      order.push(current);

      (adj[current] || []).forEach((child) => {
        inDegree[child]--;
        if (inDegree[child] === 0) {
          queue.push(child);
        }
      });
    }

    if (order.length < entityNames.length) {
      const cycleNodes = entityNames.filter((name) => !order.includes(name));
      return {
        isValid: false,
        order: [],
        cycleNodes,
        errorMessage: `Circular dependency detected among entities: [${cycleNodes.join(' ⇄ ')}]`
      };
    }

    return { isValid: true, order };
  },

  generateData: async () => {
    const { entities, activeLocales, policy, sinks, validateDAG } = get();
    const dagResult = validateDAG();

    if (!dagResult.isValid) {
      set({ error: dagResult.errorMessage });
      return;
    }

    set({ isGenerating: true, error: null });

    const payload: GenerateRequest = {
      name: get().schemaName,
      locales: activeLocales,
      entities,
      policy,
      sinks
    };

    try {
      const res = await fetch('http://localhost:8000/api/v1/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Unknown generation failure' }));
        const msg = typeof errorData.detail === 'object' ? errorData.detail.message : errorData.detail;
        throw new Error(msg || `Server error: ${res.statusText}`);
      }

      const result: GenerateResponse = await res.json();
      set({
        generationResult: result,
        isGenerating: false,
        activeTab: 'results',
        error: null
      });
    } catch (err: any) {
      set({
        isGenerating: false,
        error: err.message || 'Failed to connect to backend engine at http://localhost:8000'
      });
    }
  },

  fetchSavedSchemas: async () => {
    set({ savedSchemasLoading: true });
    try {
      const res = await fetch(`${API_BASE}/api/v1/schemas`);
      if (!res.ok) throw new Error(`Registry listing failed: ${res.statusText}`);
      const body = await res.json();
      set({ savedSchemas: body.schemas, savedSchemasLoading: false });
    } catch (err: any) {
      console.warn('Schema registry unavailable:', err.message);
      set({ savedSchemas: [], savedSchemasLoading: false });
    }
  },

  saveSchema: async (options = {}) => {
    const state = get();
    const name = (options.name ?? state.schemaName ?? '').trim();
    if (!name) {
      set({ error: 'A schema name is required to save.' });
      return 'failed';
    }

    // Refresh the registry listing so the overwrite check reflects current state
    // (avoids silently overwriting names we haven't seen)
    await get().fetchSavedSchemas();

    if (!options.silentOverwrite) {
      const fresh = get().savedSchemas.find((s) => s.name === name);
      if (fresh && !window.confirm(`Saved Schema "${name}" already exists. Overwrite it?`)) {
        return 'cancelled';
      }
    }

    const dbml_source = options.dbmlSource !== undefined
      ? options.dbmlSource
      : (state.dbmlSource ?? null);

    const payload = {
      name,
      origin: options.origin ?? ('canvas' as const),
      dbml_source,
      snapshot: buildSnapshot({ ...state, schemaName: name })
    };

    try {
      const res = await fetch(`${API_BASE}/api/v1/schemas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Unknown registry failure' }));
        const msg = typeof errorData.detail === 'object'
          ? errorData.detail.message ?? 'Registry rejected the save'
          : String(errorData.detail);
        throw new Error(msg);
      }

      // Optimistically refresh the listing from the authoritative response
      const savedSchemas = get().savedSchemas.filter((s) => s.name !== name);
      const now = new Date().toISOString();
      savedSchemas.unshift({
        name,
        origin: payload.origin,
        entity_count: state.entities.length,
        created_at: now,
        updated_at: now
      });
      set({
        savedSchemas,
        isDirty: false,
        error: null,
        schemaName: name
      });
      return 'saved';
    } catch (err: any) {
      set({ error: err.message || 'Failed to save schema to the registry' });
      return 'failed';
    }
  },

  loadSavedSchema: async (name) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/schemas/${encodeURIComponent(name)}`);
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === 'string' ? detail.detail : `Saved Schema "${name}" not found`
        );
      }
      const record = await res.json();
      const snap = record.snapshot ?? {};

      set({
        entities: JSON.parse(JSON.stringify(snap.entities ?? [])),
        activeLocales: snap.locales?.length ? snap.locales : ['en_US'],
        policy: { ...get().policy, ...(snap.policy ?? {}) },
        sinks: { ...get().sinks, ...(snap.sinks ?? {}) },
        schemaName: snap.name ?? record.name,
        selectedEntityIndex: 0,
        generationResult: null,
        error: null,
        isDirty: false,
        dbmlSource: record.dbml_source ?? null,
        activeTab: 'builder'
      });
      return true;
    } catch (err: any) {
      set({ error: err.message || 'Failed to load saved schema' });
      return false;
    }
  },

  deleteSavedSchema: async (name) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/schemas/${encodeURIComponent(name)}`, {
        method: 'DELETE'
      });
      if (!res.ok && res.status !== 204) {
        throw new Error(`Failed to delete "${name}" (${res.status})`);
      }
      set((state) => ({ savedSchemas: state.savedSchemas.filter((s) => s.name !== name) }));
      return true;
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete saved schema' });
      return false;
    }
  }
}));

