# Saved Dataset Row Persistence: Options Research

Ticket: `.scratch/saved-dataset/issues/02-row-persistence-technology.md` · Date: 2026-10-28
Scope: where the **rows** of a Saved Dataset live on disk, options A (DuckDB file), B (SQLite), C (Parquet/CSV), plus where derived artifact bytes should live. Facts first, recommendation second.

## 1. Facts from the codebase

### 1.1 What rows look like

- The engine emits rows as plain Python dicts: `GeneratedDataset.records: Dict[str, List[Dict[str, Any]]]` (`apps/api/app/core/engine.py:32`), one list per entity, in topological execution order.
- Generators produce **JSON-primitive values**: strings, ints, floats, None, bools. Notably, the `date_time` generator returns a **string** via `strftime` (`apps/api/app/core/registry.py:191-197`) — there are no typed datetimes in the row dicts. This narrows the "date round-trip" concern: dates arrive as pre-formatted strings, so no storage option needs a real `TIMESTAMP` type to preserve fidelity, though typed columns would *add* type info.
- Columns can be **mixed-typed** (noise injection can put `"123_CORRUPTED"` next to integers in one column) — this is precisely why `ParquetExporter._build_table` coerces str+num columns to string before Arrow infers types (`apps/api/app/exporters/parquet.py:35-49`).
- PK pools are consumed during generation only (`engine.py:68,124`); they are not needed after rows exist.

### 1.2 What the DuckDB mock-API path does today

`apps/api/app/exporters/duckdb_api.py`:

- Class-level cache `_instances: Dict[str, duckdb.DuckDBPyConnection]` (`duckdb_api.py:17`) lazily holding `duckdb.connect(":memory:")` (`duckdb_api.py:23`). **There is no `close` anywhere in the codebase**; connections and their rows live and die with the process — restart loses every persisted schema (and `uvicorn` in dev runs with `--reload`, `run_dev.sh:46`, so a code edit alone drops them).
- Persistence inserts via a pandas round-trip: `df = pd.DataFrame(records)` → `conn.register("df_temp", df)` → `CREATE OR REPLACE TABLE ... AS SELECT * FROM df_temp` → `unregister` (`duckdb_api.py:31-38`).
- Serving is raw SQL pagination: `SHOW TABLES` check (`:52-56`), `SELECT COUNT(*)` (`:59`), `SELECT * ... LIMIT {limit} OFFSET {offset}` → `.fetch_df()` (`:62-64`), then null-mapping with `df.where(pd.notnull(df), None).to_dict(orient="records")` for JSON serialization (`:67`). Endpoint inputs: `limit` capped at `ge=1, le=1000`, `offset ge=0` (`apps/api/app/main.py:270-271`).
- Wired from `/api/v1/generate` at `main.py:175`; mock endpoints at `main.py:257-285` are **synchronous `def` handlers** (as is generation, `main.py:81`), so FastAPI runs them on the AnyIO worker-thread pool — blocking calls of tens-of-ms are acceptable on this path and don't block the event loop.
- Same-process concurrent use of one shared connection is **already unsafe**: in duckdb 2.0.0, overlapping calls on a single connection raise `ResourceInUseException: connection is busy with another call; it refuses instead of waiting, so use a separate connection from cursor()` (empirical: 15 of 16 concurrently reading threads failed). For the current in-memory fast path this rarely surfaces, but it's the pattern the `_instances` cache enforces.

### 1.3 What SQLite does today (Schema Registry)

`apps/api/app/core/schema_registry.py`:

- A single SQLite file via `default_db_path()`: env override `SCHEMA_REGISTRY_DB`, else `/app/data/schema_registry.db` when containerized, else `data/api/schema_registry.db` (`schema_registry.py:30-37`). The `./data/api:/app/data` docker volume makes it restart-safe (`docker-compose.yml:13`).
- Connection style: **short-lived, per-method, context-managed** connections (`_connect()` `schema_registry.py:49-52`; used at `:46-47`, `:67`, `:92`, `:112`, `:129`). No cross-thread connection sharing anywhere — clean to emulate.
- ADR-0001 (`docs/adr/0001-sqlite-schema-registry.md:3,7`) scopes SQLite to the *registry*: it explicitly rejects reusing DuckDB for the registry because "the DuckDB mock-API store is per-generation and disconnected; bolting a registry onto it conflates two unrelated lifetimes". The same lifetime argument cuts the other way for *rows*: the Saved Dataset is a separate object with a separate lifetime from either the registry or the ephemeral mock store.

### 1.4 Vendored dependencies

`apps/api/requirements.txt` floors vs. installed in `apps/api/.venv` (local dev; Dockerfile uses `python:3.11-slim`, `apps/api/Dockerfile:1`):

| Package | Floor | Installed (venv, Python 3.15) |
|---|---|---|
| duckdb | `>=0.10.0` (line 6) | **2.0.0** |
| pandas | `>=2.2.0` (line 7) | **3.1.0** |
| pyarrow | `>=15.0.0` (line 9) | **26.0.0** |
| openpyxl | `>=3.1.2` (line 8) | **3.1.5** |
| fastapi | `>=0.110.0` (line 1) | 0.159.1 |
| sqlite3 | stdlib (Docker 3.11 / venv 3.15) | SQLite **3.53.4** |

All three option-critical libraries are already vendored; **no new dependency is needed for any option**.

### 1.5 Empirical results (these exact versions, one-shot scripts)

**Pandas round-trip fidelity** — dict rows → `pd.DataFrame` → format → `pd.read_*`:

| Column value | Parquet back | CSV back |
|---|---|---|
| Int (no NaN col) | `int64` preserved | `int64` preserved |
| Int column with a NaN | `float64` (pandas coercion, unchanged by parquet) | `float64` |
| Float + NaN | `float64`, NaN round-trips | `float64`, NaN round-trips |
| Unix/Arabic unicode strings | `str` preserved exactly | `str` preserved exactly |
| `pd.Timestamp("2026-01-05")` | `datetime64[us]` **preserved** | **string** `"2026-01-05"` |
| Mixed int+str column | **`to_parquet` raises** `ArrowTypeError: Expected bytes, got a 'int' object` unless coerced (hence `parquet.py:35-49`) | becomes two strings, silent type loss |

**DuckDB file-backed restart simulation** — `duckdb.connect(path)`, `register` → `CREATE TABLE`, `close()`, new process connects and selects: dtypes fully preserved through a real close/reopen, including `datetime64[us]` → Timestamps, NaN → None. Pagination SQL (`LIMIT`/`OFFSET`) is unchanged by file vs memory.

**SQLite speed at this workload** — 20,000-row / 4-col table, synchronous Python:

| Query | SQLite 3.53.4 |
|---|---|
| `SELECT COUNT(*)` | 0.1 ms |
| `LIMIT 100 OFFSET 5000` page → list | 0.3 ms |
| full 20k rows → dicts | ~65 ms |

At 10k+ rows/entity with `limit ≤ 1000` pages, SQLite on the sync threadpool is comfortably fast; the pages served by `query_paginated` will never be the 20k-row full scan.

**DuckDB concurrency** (same file, one process): one *shared* connection across threads → `ResourceInUseException` (above); **per-thread / separate connections → zero errors** (8 threads × 200 reads); two connections to the same file in one process both work. **Cross-process**: the second process gets `IOException: Could not set lock on file ... Conflicting lock is held` while the first has the file open; after `close()` it succeeds. So: file lock is a *one-open-process-at-a-time* constraint.

**ADR intent mismatch**: `docs/adr/0001-duckdb-backed-mock-api.md:3` states the DuckDB store should provide "persistent mock data across worker restarts" — the `:memory:` implementation (`duckdb_api.py:23`) does not do that today. Option A is the implementation that would deliver the ADR as written.

## 2. Options compared

### Option A — one DuckDB file per saved dataset

`data/api/datasets/<schema_id>/<dataset_id>.duckdb` (under the already-mounted `./data/api:/app/data`, `docker-compose.yml:13`), pointing `duckdb.connect` at a real path instead of `":memory:"`.

*What survives untouched:* the write path (`pd.DataFrame(records)` → register → `CREATE TABLE`, `duckdb_api.py:31-38`), pagination SQL (`:59-64`), catalog (`:79-95`), the `/api/v1/mock/**` contract, and null-mapping for JSON (`:67`). No new library.

*Lifecycle changes the `_instances` cache needs:*
1. **Cache file paths, not connections.** Rename/split into a per-dataset path index; open lazily. On a fresh process the first `SHOW TABLES` / `COUNT(*)` re-opens the file and everything below it works — restart-safe by construction.
2. **Add explicit `close()`** (or open-per-call). Because DuckDB holds an exclusive file lock, a connection left open blocks: other processes (a second uvicorn worker, the test suite) would get the `IOException` lock error. Opening per call (like `SchemaRegistry._connect`, `schema_registry.py:49-52`) also removes today's never-closed `_instances` leak.
3. **Stop sharing one connection across requests.** Reuse either `threading.local` connections or `conn.cursor()` per request; per-thread connections empirically error-free, shared ones raise under duckdb 2.0. This fix is needed for the in-memory path too, not just for files.
4. **Document the one-writer-process assumption** (single uvicorn worker in both `Dockerfile:12` and `run_dev.sh:46`), matching the single-user deployment in ADR-0001 sqlite (`docs/adr/0001-sqlite-schema-registry.md:3`).
5. **404 wiring stays**: `get_catalog` already funnels exceptions into a 404 (`main.py:258-263`); a lazily-opened file that never exists (never generated) is simply a 404, same as today after restart.

### Option B — SQLite (rows in the registry DB or a sibling file)

Adequate on raw speed (empirically 0.1ms count / 0.3ms page-100 at 20k rows, well inside the sync threadpool; 10k+ rows/entity is not a bottleneck). But:

- **Two storage technologies on the request path** instead of one. Rows would be written into SQLite (dicts → `INSERT ... executemany`, JSON glue for nested values), while the API sink path already delivers rows to DuckDB through `persist_dataset` (`duckdb_api.py:27-38`); the mock endpoints would then read rows back out of a *different* engine and re-serialize to dicts — a duplicated persistence path where the pipeline already has one.
- **Type fidelity**: SQLite stores TEXT/INTEGER/REAL/NULL (dynamic typing); emulating typed columns requires maintaining a `CREATE TABLE` per entity built from the generator registry's `sql_type`s (`apps/api/app/core/registry.py`) — a new schema-maintenance problem the DuckDB option gets for free from pandas + `register` inference (and DuckDB handles the mixed `123_CORRUPTED` columns by scanning as VARCHAR, the same coercion `parquet.py:35-49` does for the parquet sink).
- **Lifetime hygiene**: ADR-0001 (`docs/adr/0001-sqlite-schema-registry.md:7`) deliberately separated registry from *rows* lifetimes. Putting rows in that file (or in a second SQLite file) re-couples the "named canvas snapshots" that ADR just unwound, and the Saved Dataset object is per-run, per-schema — a natural fit for one file per dataset, not one table keyed by dataset_id.

Not rejected on performance — rejected on duplication and lifetime coupling.

### Option C — Parquet/CSV files

The sinks already produce exactly these formats: `ParquetExporter.export_tables` (`parquet.py:17-32`, snappy) and `CsvZipExporter.export_to_zip` (`csv_zip.py:15-34`, stdlib `csv.DictWriter`).

- **Parquet round-trip** is *good but not free*: dtypes preserved including `datetime64[us]`, but mixed-type columns **must** reuse the str-coercion of `parquet.py:35-49` or `to_parquet` raises (`ArrowTypeError: Expected bytes, got a 'int' object`, empirical). Int-column-with-NaN → `float64`, unchanged by any option here (it's the `pd.DataFrame` front-door behavior first seen in `duckdb_api.py:34`).
- **CSV round-trip** loses typing silently (numbers-as-strings on read-back unless re-inferred; dates are strings, which barely matters — the engine emits dates as `strftime` strings already, `registry.py:197`; unicode survives both).
- Serving from CSV/Parquet means **re-implementing pagination in pandas** (`df.iloc[offset:offset+limit]`) instead of SQL, plus a new file-per-entity discovery problem (the DuckDB path gets a one-line `SHOW TABLES` catalog for free, `duckdb_api.py:52-54,83-95`).

A real middle path exists — write **Parquet per entity** and serve with DuckDB `read_parquet('<file>')` over per-dataset connection — but it adds extra fixture files and moves you no closer to SQL-native pagination than one `.duckdb` file that already contains the same tables.

## 3. Where derived artifact bytes (Excel, SQL dumps, ...) live

Today they're held in process memory: `_ARTIFACT_STORE: Dict[str, Dict[str, Dict[str, Any]]]` at `main.py:48`, populated per generate request (`main.py:100-171`), streamed by `/api/v1/download/...` (`main.py:287-302`). Like the in-memory DuckDB store, they vanish on restart, and the dict is never evicted (unbounded process growth).

Facts relevant to the decision:
- SQL dumps are cheap strings — `PostgresExporter.generate_ddl_and_dml(dataset, request)` (`main.py:105`) regenerates deterministically from rows.
- Excel is openpyxl-bound (expensive-ish at scale, but the repo already ships this exporter: `apps/api/app/exporters/excel.py`, `openpyxl 3.1.5`).
- Once rows persist, **artifact bytes are derivable**; storing them is redundant state that can drift from rows (ticket 01 also flags this: store bytes only if expensive to re-derive).

Recommendation: **rows on disk are canonical, artifacts are re-derived per download** from the persisted rows; retire `_ARTIFACT_STORE`. Excel can be re-derived at download time (fine for 10k-row datasets; add a small on-disk cache only if profiling shows need). This keeps "Saved Dataset = rows + generation params" and avoids a duplicate-asset drift problem entirely — matching ticket `01-what-is-a-saved-dataset.md`'s recommended split.

## 4. Recommendation (comparative)

**Option A — one DuckDB file per saved dataset** is the best fit:

1. **It completes stated intent**: ADR-0001 duckdb (`docs/adr/0001-duckdb-backed-mock-api.md:3`) already claims "persistent mock data across worker restarts"; the `:memory:` implementation just hasn't done it. File-backed is the smallest delta — swap `":memory:"` for a path, add close discipline (`duckdb_api.py:23`).
2. **Zero new dependencies**: duckdb, pandas, pyarrow all already vendored (`requirements.txt:6,7,9`), versions covered by the floors (duckdb 2.0.0 ≥ 0.10.0 etc.).
3. **The serving code is SQL-native already**: `SHOW TABLES` / `COUNT(*)` / `LIMIT OFFSET` (`duckdb_api.py:52-64`) and the whole `query_paginated` contract carry over unchanged; no pandas-slicing pagination layer to write.
4. **One dataset = one file** matches the per-dataset lifetime and the per-schema directory layout that ticket 03 ("where saved datasets live") needs; mirrors the keying of `default_db_path()` (`schema_registry.py:30-37`) with an env-overridable directory like `DATASET_STORE_DIR`.
5. **Type fidelity is proven empirically**: pandas → DuckDB table → reopen → `fetch_df` round-trips `datetime64[us]`, floats-with-NaN, and unicode exactly; only the mixed/noise-corrupted columns coerce to string, identical to what `parquet.py:35-49` already does for the parquet sink.

**Not B (SQLite)**: fast enough at this scale (empirically confirmed) but forces a second storage engine and a hand-maintained typed-schema layer, and re-couples lifetimes that ADR-0001 deliberately kept separate.

**Not C (Parquet/CSV) alone**: fine as a *bulk export* format (already ships as sinks), but as a serving store it loses the SQL catalog/free-typed `SHOW TABLES`/`COUNT`/`LIMIT` pattern and re-imports either pandas slicing or a tiny DuckDB reader. If bulk cold-storage or interop with the rest of the data stack is ever needed, Parquet-per-entity (served via `read_parquet`) is a clean later migration — a `.duckdb` file can always export its tables to Parquet one per entity, so choosing A doesn't preclude C.

Concrete follow-ups for an implementing ticket (out of scope here, listed because they're the diffs option A implies):
- `duckdb_api.py`: replace `_instances` connection cache with a path index + per-request/thread connections (`threading.local` or `cursor()`), add `close()`, accept a base directory env var.
- `main.py`: pass a stable dataset id (derived from `schema_id` + generation run) into `persist_dataset` (`main.py:175`); retire `_ARTIFACT_STORE` (`main.py:48`) when download endpoints re-derive from rows.
- Docker volume is already correct (`docker-compose.yml:13`); no config change.
