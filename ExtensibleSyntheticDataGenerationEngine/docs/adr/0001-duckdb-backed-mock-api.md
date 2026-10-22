# DuckDB-Backed Mock API and Ephemeral Dataset Storage

We chose an embedded DuckDB instance scoped by schema ID (`/api/v1/{schema_id}/{table_name}`) to back dynamically exposed mock REST endpoints rather than holding in-memory Python dictionaries. DuckDB provides zero-copy columnar performance, SQL-based `LIMIT`/`OFFSET` pagination, persistent mock data across worker restarts, and process memory protection when generating hundreds of thousands of rows.

