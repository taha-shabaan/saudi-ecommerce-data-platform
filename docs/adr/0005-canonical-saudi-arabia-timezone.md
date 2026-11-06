# 0005: Canonical Saudi Arabia Operational Timezone (Asia/Riyadh / AST)

We decided to standardize all timestamps, incremental watermark states, S3 partition dates (`year=YYYY/month=MM/day=DD`), and structured logging exclusively on Saudi Arabia Time (`Asia/Riyadh` / AST: UTC+3, fixed offset without daylight saving time), eliminating UTC dependencies across ingestion and storage.

Operating eCommerce across the Kingdom of Saudi Arabia requires operational alignment with local business days and diurnal shopping patterns (such as nocturnal Ramadan shopping from 22:00 to 04:00 AST). Partitioning and tracking in UTC fragmented late-night domestic activity across multiple calendar dates, introduced timezone reconciliation overhead between OLTP databases and 3PL courier feeds, and created operational discrepancies in executive dashboards. Centralizing on `Asia/Riyadh` ensures deterministic date boundaries, simplifies partition pruning, and unifies operational visibility.
