# Synthetic Data Generation Engine

The domain of designing relational schemas, resolving topological dependencies, generating localized mock data, and dispatching datasets to export sinks.

## Language

**Schema**:
The blueprint specifying a relational collection of entities, attribute definitions, constraints, and generation targets.
_Avoid_: Database config, DDL template, data model

**Entity**:
A named data resource or model within a schema with a defined target record count and attribute list.
_Avoid_: Table, relation, worksheet, collection

**Attribute**:
A discrete field or property specification within an entity defining its data generator type, nullability, and primary key flag.
_Avoid_: Column, field, property

**Generator**:
A strategy and configuration producing synthetic data points for an attribute.
_Avoid_: Mock provider, faker function, data type

**Relationship**:
A directed foreign key dependency linking a child attribute to a parent entity's primary key attribute.
_Avoid_: Reference, foreign key constraint, join

**Locale Binding**:
The assignment of a cultural and geographical locale to an entire record to maintain consistency across localized attributes.
_Avoid_: Country tag, regional setting, faker locale

**Primary Key Pool**:
The collection of generated unique identifier values from a parent entity used to sample valid foreign keys for child entities.
_Avoid_: ID cache, key reservoir, foreign key pool

**Export Sink**:
A target destination or packaging format for generated data, including relational databases (PostgreSQL), columnar stores (Parquet), tabular files (Excel, CSV), structured documents (JSON), and dynamic mock REST APIs.
_Avoid_: Output format, destination, data adapter

**Sink Artifact**:
A generated output file or endpoint resource produced by an export sink, such as an Excel workbook, a zipped CSV collection, a SQL script, or a dynamic REST route.
_Avoid_: Result file, dump, export asset

**Dependency Graph**:
The directed acyclic graph mapping foreign key constraints between tables to determine valid topological generation order.
_Avoid_: Execution tree, table flow, relation graph

**Starter Template**:
A curated, pre-configured schema representing standard domain models used to initialize generation workflows.
_Avoid_: Sample schema, preset, demo project

**Saved Schema**:
A named snapshot of the complete canvas configuration — entities, relationships, target locales, consistency policy, and sink configuration — persisted so the same working state can be retrieved later by name, regardless of how the schema was created (upload, template, or hand-built).
_Avoid_: Imported file, backup, project

**Schema Registry**:
The persistent store holding saved schemas, keyed by unique schema name, that survives system restarts.
_Avoid_: Artifact store, cache, upload history

**Saved Dataset**:
The generated rows, generation parameters, and metrics of one generation run, persisted as a distinct identifiable version belonging to a saved schema, so artifacts can be re-derived and served after restarts.
_Avoid_: Output file, cached result, export asset, backup

**Dataset Registry**:
The persistent store holding saved datasets, newest-first per schema, that survives system restarts.
_Avoid_: Cache, artifact store, schema registry

**Consistency Policy**:
A configurable rule set governing the degree of relational integrity, locale coherence, and data cleanliness enforced during generation.
_Avoid_: Validation level, quality rule, data rule

**Orphan Injection**:
The deliberate production of foreign key values that do not exist within the parent table's primary key pool to test referential integrity edge cases.
_Avoid_: Broken reference, ghost key, dangling reference

**Data Noise**:
Controlled anomalies introduced into generated data points, such as untrimmed whitespace, sentinel null representations, and malformed strings.
_Avoid_: Dirty data, data corruption, fuzzing

