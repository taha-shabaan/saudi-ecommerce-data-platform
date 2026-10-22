# Generic Entity-Attribute Model with Multi-Format Resource Sinks

We transitioned the conceptual model from SQL-specific "tables and columns" to generic "entities and attributes", expanding export sinks to natively support Apache Parquet and JSON alongside PostgreSQL, Excel (.xlsx), CSV (.csv/.zip), and dynamic Mock REST APIs. This decouples the core generator from relational database semantics, allowing the same topological schema to populate modern columnar data lakes (Parquet), document pipelines (JSON), and traditional relational OLTP targets.

