# SQLite for the Schema Registry

Schemas (Saved Schemas, see GLOSSARY.md) are persisted in a single SQLite file mounted into the API container via a docker volume (`./data/api:/app/data`), not in a Postgres service. Context: the engine previously held all state in memory and lost every schema on restart, and the product's own "PostgreSQL sink" is an *export target that generates SQL scripts* — it never stores engine data. Decision: SQLite gives restart-safe persistence with zero new services in docker-compose; a Postgres service adds operational surface this single-user deployment doesn't need.

Considered options:
- **Postgres service in docker-compose** — rejected: more moving parts, and nothing here needs concurrent multi-writer access or advanced types. Revisit if multi-user support (currently an explicit no) or shared registry access ever arrives.
- **DuckDB reuse** — rejected: the DuckDB mock-API store is per-generation and disconnected; bolting a registry onto it conflates two unrelated lifetimes.
