# Configurable Consistency Policies and Controlled Data Noise

We chose to support user-configurable Consistency Policies (Strict, Mild Inconsistency, and Chaos/Stress Test) and explicit noise injection parameters (orphan foreign key generation, locale drift, and string/format corruption). This enables data engineers to test ETL resilience, data cleaning pipelines, and error handling with realistic "dirty" data rather than artificially pristine records.

