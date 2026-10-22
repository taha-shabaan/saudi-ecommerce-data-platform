# Dual PostgreSQL Export Strategy

We chose to support dual PostgreSQL export modes: direct streaming ingestion into a user-specified connection string using `asyncpg`, alongside generating a standalone, downloadable `.sql` migration script containing DDL schema definitions and batched `INSERT` statements in topological dependency order. This enables both direct cloud database population and offline, version-controlled database migrations without requiring network ingress.

