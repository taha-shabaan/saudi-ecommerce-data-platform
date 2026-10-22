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

  // Actions
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

  setSelectedEntityIndex: (index) => set({ selectedEntityIndex: index }),
  setActiveTab: (tab) => set({ activeTab: tab }),

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
        selectedEntityIndex: state.entities.length
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
      return { entities: sanitized, selectedEntityIndex: newIndex };
    });
  },

  setEntityRecordCount: (index, count) => {
    set((state) => {
      const entities = [...state.entities];
      if (entities[index]) {
        entities[index] = { ...entities[index], record_count: Math.max(1, count) };
      }
      return { entities };
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
      return { entities };
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
      return { entities };
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
      return { entities };
    });
  },

  toggleLocale: (locale) => {
    set((state) => {
      const exists = state.activeLocales.includes(locale);
      if (exists) {
        if (state.activeLocales.length === 1) return state; // Keep at least one
        return { activeLocales: state.activeLocales.filter((l) => l !== locale) };
      }
      return { activeLocales: [...state.activeLocales, locale] };
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
      }
    });
  },

  updatePolicy: (updates) => {
    set((state) => ({
      policy: { ...state.policy, ...updates }
    }));
  },

  toggleSink: (sinkKey) => {
    set((state) => {
      if (typeof state.sinks[sinkKey] === 'boolean') {
        return {
          sinks: {
            ...state.sinks,
            [sinkKey]: !state.sinks[sinkKey]
          }
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
        selectedEntityIndex: 0,
        generationResult: null,
        error: null
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
      name: 'Synthetic Relational Dataset',
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
  }
}));
