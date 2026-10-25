# 0002: Track Customer Profile Mutations with SCD Type 2 via dbt Snapshots

We decided to model `dim_customers` as a Slowly Changing Dimension Type 2 (SCD2) utilizing `dbt snapshot` with `valid_from`, `valid_to`, and `is_current` fields, rather than overwriting customer attributes in place (SCD1).

In Saudi eCommerce, customer relocations across provinces (e.g., from Riyadh to Jeddah) and changes in contact details or loyalty tiers occur over time. Overwriting customer attributes (SCD1) causes historical orders to be misattributed to the customer's current region, corrupting regional logistics and sales metrics. Maintaining an SCD2 dimension preserves temporal fidelity for historical attribution at the cost of managing surrogate keys and validity windows in downstream fact joins.

