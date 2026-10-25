# 0001: Decouple PySpark Processing from Snowflake Loading via S3 Parquet

We decided to have PySpark write partitioned columnar Parquet files into the S3 Processed Zone, and use Snowflake's native `COPY INTO` command from an external stage to load warehouse staging tables, rather than writing directly from PySpark to Snowflake over JDBC.

Direct PySpark-to-Snowflake writes couple the lifecycle and failure domains of the Spark cluster with Snowflake compute, incur high JDBC egress overhead, and prevent re-loading historical warehouse partitions without re-running Spark compute. Decoupling through immutable Parquet files in S3 provides cost-effective intermediate checkpoints, supports independent pipeline retries, and leverages Snowflake's optimized columnar bulk loader.

