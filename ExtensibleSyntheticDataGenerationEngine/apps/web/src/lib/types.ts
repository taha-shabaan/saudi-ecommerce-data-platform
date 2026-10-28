export type GeneratorType =
  | 'autoincrement'
  | 'uuid'
  | 'full_name'
  | 'first_name'
  | 'last_name'
  | 'email'
  | 'phone'
  | 'street_address'
  | 'city'
  | 'country'
  | 'date_time'
  | 'numeric_range'
  | 'categorical'
  | 'boolean'
  | 'text'
  | 'foreign_key';

export interface AttributeDefinition {
  name: string;
  type: GeneratorType;
  is_primary_key: boolean;
  nullable: boolean;
  null_probability?: number;
  fk_target?: string; // format: "entity.attribute"
  params?: Record<string, any>;
}

export interface EntityDefinition {
  name: string;
  record_count: number;
  attributes: AttributeDefinition[];
}

export interface ConsistencyPolicy {
  preset: 'strict' | 'mild' | 'chaos';
  orphan_rate: number;
  locale_drift_rate: number;
  noise_rate: number;
  duplicate_rate: number;
}

export interface ExportSinksConfig {
  postgres: boolean;
  excel: boolean;
  csv: boolean;
  parquet: boolean;
  json: boolean;
  api: boolean;
  postgres_connection_string?: string;
  api_route_prefix?: string;
}

export interface GenerateRequest {
  schema_id?: string;
  name: string;
  locales: string[];
  entities: EntityDefinition[];
  policy: ConsistencyPolicy;
  sinks: ExportSinksConfig;
}

export interface GenerateResponse {
  schema_id: string;
  status: string;
  execution_order: string[];
  metrics: {
    duration_ms: number;
    total_entities: number;
    total_records: number;
    entity_record_counts: Record<string, number>;
  };
  artifacts: {
    dataset_id?: string;
    dataset_url?: string;
    sql?: { download_url: string; preview_snippet?: string };
    excel?: { download_url: string; sheets: string[] };
    csv?: { download_url: string };
    parquet?: { download_url: string; entities: string[] };
    json?: { download_url: string };
    api?: { catalog_url: string; sample_routes: string[] };
  };
  warnings: string[];
}

export interface CountryLocale {
  code: string;
  country: string;
  flag: string;
}

