"""
Schema and data transfer models for the Synthetic Data Generation Engine.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator
import uuid
import re


class AttributeDefinition(BaseModel):
    """
    Defines a discrete attribute within an entity.
    """
    name: str = Field(..., description="Attribute name in snake_case")
    type: str = Field(
        ...,
        description="Generator type key (e.g., autoincrement, uuid, full_name, email, phone, foreign_key, etc.)"
    )
    is_primary_key: bool = Field(default=False, description="Flag indicating if attribute is primary key")
    nullable: bool = Field(default=False, description="Whether null values can be generated")
    null_probability: float = Field(default=0.0, ge=0.0, le=1.0, description="Probability of generating null if nullable")
    fk_target: Optional[str] = Field(
        default=None,
        description="Target entity and attribute for foreign keys in format 'entity.attribute'"
    )
    params: Dict[str, Any] = Field(default_factory=dict, description="Generator-specific configuration parameters")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(r"^[a-z_][a-z0-9_]*$", clean):
            raise ValueError(f"Attribute name '{v}' must be valid identifier (snake_case)")
        return clean

    @field_validator("fk_target")
    @classmethod
    def validate_fk_target(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            parts = v.split(".")
            if len(parts) != 2:
                raise ValueError(f"Invalid fk_target '{v}'. Expected format 'entity_name.attribute_name'")
        return v


class EntityDefinition(BaseModel):
    """
    Defines an entity resource within the schema.
    """
    name: str = Field(..., description="Entity name (snake_case)")
    record_count: int = Field(default=10, ge=1, le=1_000_000, description="Target number of records to generate")
    attributes: List[AttributeDefinition] = Field(..., min_length=1, description="List of entity attributes")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(r"^[a-z_][a-z0-9_]*$", clean):
            raise ValueError(f"Entity name '{v}' must be valid identifier (snake_case)")
        return clean


class ConsistencyPolicy(BaseModel):
    """
    Controls consistency level, referential anomaly rates, and data noise injection.
    """
    preset: str = Field(default="strict", description="Preset: 'strict', 'mild', or 'chaos'")
    orphan_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Percentage (0.0 - 1.0) of foreign keys injected as orphaned IDs"
    )
    locale_drift_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Percentage (0.0 - 1.0) of records with mismatched regional attributes"
    )
    noise_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Percentage (0.0 - 1.0) of string/date attributes injected with dirty data"
    )
    duplicate_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Percentage (0.0 - 1.0) of cloned duplicate records"
    )


class ExportSinksConfig(BaseModel):
    """
    Configuration specifying which export sinks to dispatch data to.
    """
    model_config = {"protected_namespaces": ()}

    postgres: bool = Field(default=True, description="Generate PostgreSQL DDL and INSERT script")
    excel: bool = Field(default=True, description="Generate multi-tab Excel workbook (.xlsx)")
    csv: bool = Field(default=True, description="Generate zipped CSV archives (.zip)")
    parquet: bool = Field(default=True, description="Generate Apache Parquet columnar files (.parquet)")
    json_export: bool = Field(default=True, alias="json", description="Generate JSON structured documents (.json)")
    api: bool = Field(default=True, description="Register dynamic Mock REST API endpoints")
    postgres_connection_string: Optional[str] = Field(
        default=None,
        description="Optional live PostgreSQL connection URI for direct insertion"
    )
    api_route_prefix: str = Field(default="/api/v1/mock", description="Prefix for dynamic REST endpoints")


class GenerateRequest(BaseModel):
    """
    Inbound generation request payload.
    """
    schema_id: Optional[str] = Field(
        default=None,
        description="Optional unique schema identifier. Auto-generated if omitted."
    )
    name: str = Field(default="Synthetic Dataset", description="User-friendly name of this dataset schema")
    locales: List[str] = Field(
        default=["en_US"],
        min_length=1,
        description="List of target country Faker locales (e.g., ar_EG, en_US, de_DE, fr_FR, ar_SA)"
    )
    entities: List[EntityDefinition] = Field(..., min_length=1, description="List of schema entities")
    policy: ConsistencyPolicy = Field(default_factory=ConsistencyPolicy)
    sinks: ExportSinksConfig = Field(default_factory=ExportSinksConfig)


class DbmlImportRequest(BaseModel):
    """
    Inbound DBDiagram.io schema import payload.
    """
    name: str = Field(..., min_length=1, max_length=120, description="Project name for the imported schema")
    source: str = Field(..., min_length=1, description="Raw DBDiagram.io DBML syntax document")


class DbmlImportResponse(BaseModel):
    """
    Outbound DBML import preview: mapped entities plus parse warnings.
    """
    name: str
    entities: List[Any]
    warnings: List[str] = Field(default_factory=list)


class SchemaSaveRequest(BaseModel):
    """
    Inbound Saved Schema upsert: full canvas snapshot keyed by unique name.
    """
    name: str = Field(..., min_length=1, max_length=120, description="Unique retrieval key for the Saved Schema")
    origin: Literal["dbml_import", "template", "canvas"] = Field(
        default="canvas", description="How the schema was created: 'dbml_import', 'template', or 'canvas'"
    )
    dbml_source: Optional[str] = Field(default=None, description="Original DBML document when origin is an import")
    snapshot: Dict[str, Any] = Field(..., description="Complete canvas configuration to restore later")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Schema name must not be blank")
        return clean


class SchemaSaveResponse(BaseModel):
    """
    Outbound result of a Saved Schema upsert.
    """
    name: str
    status: str = Field(..., description="'created' or 'updated'")
    created_at: str
    updated_at: str
    entity_count: int


class SavedSchemaListItem(BaseModel):
    """
    Compact metadata row for the Saved Schema listing (no snapshot, no source payload).
    """
    name: str
    origin: str
    entity_count: int
    created_at: str
    updated_at: str


class SavedSchemaRecord(BaseModel):
    """
    Full Saved Schema record including the snapshot for canvas restoration.
    """
    name: str
    origin: str
    dbml_source: Optional[str]
    snapshot: Dict[str, Any]
    created_at: str
    updated_at: str


class GenerateResponse(BaseModel):
    """
    Outbound response returning execution status, metrics, and artifact references.
    """
    schema_id: str
    status: str
    execution_order: List[str]
    metrics: Dict[str, Any]
    artifacts: Dict[str, Any]
    warnings: List[str] = []
