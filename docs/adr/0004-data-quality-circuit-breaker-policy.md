# 0004: Two-Tier Data Quality Policy with Hard Circuit Breakers

We decided to partition pipeline data quality tests into two tiers: Tier 1 (Critical) assertions that act as hard circuit breakers halting the Airflow DAG before downstream marts are published, and Tier 2 (Warning) assertions that log warnings and emit metrics without blocking the pipeline.

Allowing data quality failures to pass into core analytical marts corrupts executive dashboards, invalidates regional financial totals, and erodes stakeholder trust. Halting the entire pipeline for minor SLA variances, however, causes operational gridlock. Enforcing hard circuit breakers strictly for structural invariants (primary keys, foreign keys, non-negative Halala amounts, and VAT calculations) guarantees that any data reaching business stakeholders is verifiably clean and reconciled.

