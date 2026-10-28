"""
FastAPI Application Entrypoint for Synthetic Data Engine.
"""

from typing import Any, Dict, List, Optional
import io
import zipfile
import uuid
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

from app.models.schema import (
    GenerateRequest, GenerateResponse, DbmlImportRequest, DbmlImportResponse,
    SchemaSaveRequest, SchemaSaveResponse, SavedSchemaListItem, SavedSchemaRecord
)
from app.core.resolver import CircularDependencyError, MissingEntityReferenceError
from app.core.dbml import parse_dbml, DbmlParseError
from app.core.engine import DataEngine, GeneratedDataset
from app.core.dataset_registry import get_dataset_registry
from app.core.registry import GeneratorRegistry
from app.core.schema_registry import get_registry
from app.exporters import (
    PostgresExporter,
    ExcelExporter,
    CsvZipExporter,
    ParquetExporter,
    JsonDocExporter,
    DuckDBApiManager
)

app = FastAPI(
    title="Extensible Synthetic Data Generation Engine",
    description="Production-grade platform for relational synthetic data generation with multi-locale coherence and controlled inconsistency.",
    version="1.0.0"
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Generated rows are persisted per generation by the Dataset Registry
# (app.core.dataset_registry); artifacts are re-derived per download request.


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:
    """Converts unhandled errors into a 500 JSON response so CORS headers are preserved."""
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/v1/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "synthetic-data-engine"}


@app.get("/api/v1/generators")
def list_generators() -> Dict[str, Any]:
    """Returns all registered synthetic generator types with metadata."""
    generators_list = []
    for name in GeneratorRegistry.list_generators():
        meta = GeneratorRegistry.get_meta(name)
        if meta:
            generators_list.append({
                "name": meta.name,
                "sql_type": meta.sql_type,
                "parquet_type": meta.parquet_type,
                "localized": meta.localized,
                "description": meta.description
            })
    return {"generators": generators_list}


@app.post("/api/v1/generate", response_model=GenerateResponse)
def generate_dataset(request: GenerateRequest) -> GenerateResponse:
    """
    Primary generation endpoint: resolves topological dependencies,
    generates synthetic data across chosen locales, and dispatches to sinks.
    """
    schema_id = request.schema_id or f"sch_{uuid.uuid4().hex[:10]}"
    request.schema_id = schema_id

    engine = DataEngine()
    try:
        dataset = engine.generate(request)
    except CircularDependencyError as e:
        raise HTTPException(status_code=400, detail={"error": "CIRCULAR_DEPENDENCY", "message": str(e)})
    except MissingEntityReferenceError as e:
        raise HTTPException(status_code=400, detail={"error": "MISSING_ENTITY_REFERENCE", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "GENERATION_ERROR", "message": str(e)})

    # Persist this generation as a Saved Dataset before any sink packaging so
    # rows, generation parameters, and metrics are all reusable later on.
    saved = get_dataset_registry().save(schema_id, dataset, request)
    dataset_id = saved["dataset_id"]
    download_root = f"/api/v1/download/{schema_id}"

    artifacts: Dict[str, Any] = {
        "dataset_id": dataset_id,
        "dataset_url": f"/api/v1/datasets/{schema_id}",
    }

    # PostgreSQL preview remains request-time so the response shows a snippet
    if request.sinks.postgres:
        sql_content = PostgresExporter.generate_ddl_and_dml(dataset, request)
        artifacts["sql"] = {
            "download_url": f"{download_root}/sql?dataset_id={dataset_id}",
            "preview_snippet": sql_content[:1000] + ("\n..." if len(sql_content) > 1000 else "")
        }

    if request.sinks.excel:
        artifacts["excel"] = {
            "download_url": f"{download_root}/excel?dataset_id={dataset_id}",
            "sheets": dataset.execution_order
        }

    if request.sinks.csv:
        artifacts["csv"] = {
            "download_url": f"{download_root}/csv?dataset_id={dataset_id}"
        }

    if request.sinks.parquet:
        artifacts["parquet"] = {
            "download_url": f"{download_root}/parquet?dataset_id={dataset_id}",
            "entities": dataset.execution_order
        }

    if request.sinks.json_export:
        artifacts["json"] = {
            "download_url": f"{download_root}/json?dataset_id={dataset_id}"
        }

    if request.sinks.api:
        artifacts["api"] = {
            "catalog_url": f"/api/v1/mock/{schema_id}",
            "sample_routes": [
                f"/api/v1/mock/{schema_id}/{ent}?limit=10&offset=0"
                for ent in dataset.execution_order
            ]
        }

    return GenerateResponse(
        schema_id=schema_id,
        status="success",
        execution_order=dataset.execution_order,
        metrics=dataset.metrics,
        artifacts=artifacts,
        warnings=dataset.warnings
    )


@app.post("/api/v1/schemas/import-dbml", response_model=DbmlImportResponse)
def import_dbml_schema(request: DbmlImportRequest) -> DbmlImportResponse:
    """
    Imports a DBDiagram.io (DBML) schema document into engine entities.
    Fails with line-numbered diagnostics when the document cannot be mapped.
    """
    try:
        result = parse_dbml(request.source, fallback_name=request.name)
    except DbmlParseError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "DBML_PARSE_ERROR", "message": str(e), "diagnostics": [
                {"line": d.line, "message": d.message} for d in e.diagnostics
            ]}
        )

    return DbmlImportResponse(name=result.name, entities=result.entities, warnings=result.warnings)


@app.post("/api/v1/schemas", response_model=SchemaSaveResponse)
def save_schema(request: SchemaSaveRequest, response: Response) -> SchemaSaveResponse:
    """
    Upserts a Saved Schema keyed by its unique name (overwrite on conflict).
    Returns 201 on first save, 200 on overwrite.
    """
    record = get_registry().upsert(
        name=request.name,
        origin=request.origin,
        dbml_source=request.dbml_source,
        snapshot=request.snapshot,
    )
    if record["status"] == "created":
        response.status_code = 201
    return SchemaSaveResponse(
        name=record["name"],
        status=record["status"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        entity_count=len(record["snapshot"].get("entities", [])),
    )


@app.get("/api/v1/schemas", response_model=Dict[str, List[SavedSchemaListItem]])
def list_saved_schemas() -> Dict[str, List[SavedSchemaListItem]]:
    """Metadata for all Saved Schemas, most recently updated first."""
    return {"schemas": get_registry().list()}


@app.get("/api/v1/schemas/{name}", response_model=SavedSchemaRecord)
def get_saved_schema(name: str) -> SavedSchemaRecord:
    """Full Saved Schema record including the canvas snapshot."""
    record = get_registry().get(name)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Saved Schema '{name}' not found")
    return SavedSchemaRecord(**record)


@app.delete("/api/v1/schemas/{name}", status_code=204)
def delete_saved_schema(name: str) -> None:
    if not get_registry().delete(name):
        raise HTTPException(status_code=404, detail=f"Saved Schema '{name}' not found")


@app.get("/api/v1/mock/{schema_id}")
def get_mock_catalog(
    schema_id: str,
    dataset_id: str = Query(default=None, description="Dataset version; defaults to the newest")
) -> Dict[str, Any]:
    """Catalog endpoint listing all entities and record counts for a schema."""
    try:
        return DuckDBApiManager.get_catalog(schema_id, dataset_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Catalog error: {str(e)}")


@app.get("/api/v1/mock/{schema_id}/{entity_name}")
def query_mock_entity(
    schema_id: str,
    entity_name: str,
    limit: int = Query(default=10, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    dataset_id: str = Query(default=None, description="Dataset version; defaults to the newest")
) -> Dict[str, Any]:
    """Dynamic mock REST endpoint with SQL pagination."""
    try:
        return DuckDBApiManager.query_paginated(
            schema_id=schema_id,
            entity_name=entity_name,
            limit=limit,
            offset=offset,
            dataset_id=dataset_id
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")


@app.get("/api/v1/datasets/{schema_id}")
def list_saved_datasets(schema_id: str) -> Dict[str, Any]:
    """Metadata for every Saved Dataset generated for a schema, newest first."""
    return {"datasets": get_dataset_registry().list(schema_id)}


@app.delete("/api/v1/datasets/{schema_id}/{dataset_id}", status_code=204)
def delete_saved_dataset(schema_id: str, dataset_id: str) -> None:
    if not get_dataset_registry().delete(schema_id, dataset_id):
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' for schema '{schema_id}' not found")


_EXPORT_FILENAMES = {
    "sql": (f"{{schema}}_migration.sql", "application/sql"),
    "excel": (f"{{schema}}_data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "csv": (f"{{schema}}_csv.zip", "application/zip"),
    "parquet": (f"{{schema}}_parquet.zip", "application/zip"),
    "json": (f"{{schema}}_data.json", "application/json"),
}


def _rederive_dataset_bytes(schema_id: str, dataset_id: str, export_type: str) -> bytes:
    """Loads a saved dataset from disk and re-derives the export artifact bytes."""
    registry = get_dataset_registry()
    dataset, request = registry.rebuild(schema_id, dataset_id)

    if export_type == "sql":
        if request is None:
            raise ValueError("Dataset has no stored generation parameters to re-derive SQL from")
        return PostgresExporter.generate_ddl_and_dml(dataset, request).encode("utf-8")
    if export_type == "excel":
        return ExcelExporter.export_to_bytes(dataset)
    if export_type == "csv":
        return CsvZipExporter.export_to_zip(dataset)
    if export_type == "parquet":
        parquet_tables = ParquetExporter.export_tables(dataset)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for ent_name, pq_bytes in parquet_tables.items():
                zf.writestr(f"{ent_name}.parquet", pq_bytes)
        return zip_buf.getvalue()
    if export_type == "json":
        return JsonDocExporter.export_to_json(dataset)
    raise ValueError(f"Unknown export type '{export_type}'")


@app.get("/api/v1/download/{schema_id}/{export_type}")
def download_artifact(
    schema_id: str,
    export_type: str,
    dataset_id: str = Query(default=None, description="Dataset version; defaults to the newest")
):
    """Downloads exported artifacts, re-derived on demand from saved rows."""
    spec = _EXPORT_FILENAMES.get(export_type)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact '{export_type}' for schema '{schema_id}' not found."
        )

    registry = get_dataset_registry()
    if dataset_id is None:
        latest = registry.latest(schema_id)
        if latest is None:
            raise HTTPException(
                status_code=404,
                detail=f"No saved dataset found for schema '{schema_id}'."
            )
        dataset_id = latest["dataset_id"]

    try:
        artifact_bytes = _rederive_dataset_bytes(schema_id, dataset_id, export_type)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not downloadable: {str(e)}")

    filename = spec[1].format(schema=schema_id)
    return Response(
        content=artifact_bytes,
        media_type=spec[1],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

