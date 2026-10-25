# 0003: Idempotent Order Mutations via dbt Incremental Merge with Lookback Window

We decided to materialize `fact_orders` and `fact_payments` using dbt's `incremental_strategy='merge'` keyed on unique business keys (`order_id`, `payment_id`) with a dynamic 7-day lookback window (`updated_at >= dateadd(day, -7, current_date)`), rather than using append-only ingestion or full table refreshes.

Order fulfillment and payment settlement—specifically for Cash on Delivery (COD)—span multiple days as packages traverse distribution hubs and couriers collect cash upon delivery. Full table recomputation does not scale as transaction volumes grow, while naive append-only tables introduce duplicated order states. A 7-day merge window bounds compute costs while ensuring late status transitions (`SHIPPED` to `DELIVERED`, payment reconciliation) update existing fact rows idempotently.

