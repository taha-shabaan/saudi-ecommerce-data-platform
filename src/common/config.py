"""Configuration management using Pydantic Settings for Saudi eCommerce Data Platform.

Loads configuration from environment variables and `.env` files with strict type enforcement.
"""

from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Central application configuration validating environment variables and secrets."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # General Environment
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Runtime environment name",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Structured logger severity threshold",
    )
    default_timezone: str = Field(
        default="Asia/Riyadh",
        description="Default reporting timezone (AST, UTC+3)",
    )

    # AWS S3 Data Lake Configuration
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS IAM Access Key ID")
    aws_secret_access_key: Optional[str] = Field(default=None, description="AWS IAM Secret Access Key")
    aws_default_region: str = Field(default="me-central-1", description="Target AWS region")
    env_storage_bucket: str = Field(
        default="saudi-ecommerce-data-lake-dev",
        description="Primary S3 Data Lake bucket name",
    )

    # Snowflake Cloud Data Warehouse Configuration
    snowflake_account: Optional[str] = Field(default=None, description="Snowflake account locator/identifier")
    snowflake_user: Optional[str] = Field(default=None, description="Snowflake user")
    snowflake_password: Optional[str] = Field(default=None, description="Snowflake password")
    snowflake_role: str = Field(default="SYSADMIN", description="Default Snowflake role")
    snowflake_warehouse: str = Field(default="COMPUTE_WH", description="Snowflake virtual warehouse")
    snowflake_database: str = Field(default="SAUDI_ECOM_DW", description="Analytics database")
    snowflake_schema: str = Field(default="RAW_STAGING", description="Default landing schema")

    # Source PostgreSQL Configuration (OLTP Store)
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="saudi_ecom_orders", description="PostgreSQL database name")
    postgres_user: str = Field(default="postgres", description="PostgreSQL username")
    postgres_password: str = Field(default="postgres", description="PostgreSQL password")

    @property
    def postgres_connection_url(self) -> str:
        """Construct SQLAlchemy/psycopg2 compatible PostgreSQL connection URL."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Global singleton instance
settings = AppSettings()

