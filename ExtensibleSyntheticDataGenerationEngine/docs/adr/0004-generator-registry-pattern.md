# Typed Decorator-Based Generator Registry

We chose a decorator-based `GeneratorRegistry` with Pydantic configuration schemas for all synthetic generators rather than hardcoded `switch`/`if-else` generation blocks. Each generator registers its unique key, semantic category, output SQL data type, localization behavior, and parameter validation schema. This allows extending the engine with custom enterprise generators without modifying core graph traversal or export pipelines.

