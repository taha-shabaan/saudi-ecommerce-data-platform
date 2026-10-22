"""
FastAPI Application Entrypoint for Synthetic Data Engine.
"""

from typing import Dict, Any, Optional
import io
import zipfile
import uuid
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

from app.models.schema import GenerateRequest, GenerateResponse
from app.core.resolver import CircularDependencyError, MissingEntityReferenceError
from app.core.engine import DataEngine
from app.core.registry import GeneratorRegistry
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

# Global in-memory storage for downloadable artifacts
# { schema_id: { export_type: {"bytes": b"...", "filename": "...", "media_type": "..."} } }
_ARTIFACT_STORE: Dict[str, Dict[str, Dict[str, Any]]] = {}


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

    # Initialize artifact store for this schema
    _ARTIFACT_STORE[schema_id] = {}
    artifacts: Dict[str, Any] = {}

    # 1. PostgreSQL Sink
    if request.sinks.postgres:
        sql_content = PostgresExporter.generate_ddl_and_dml(dataset, request)
        sql_bytes = sql_content.encode("utf-8")
        _ARTIFACT_STORE[schema_id]["sql"] = {
            "bytes": sql_bytes,
            "filename": f"{schema_id}_migration.sql",
            "media_type": "application/sql"
        }
        artifacts["sql"] = {
            "download_url": f"/api/v1/download/{schema_id}/sql",
            "preview_snippet": sql_content[:1000] + ("\n..." if len(sql_content) > 1000 else "")
        }

    # 2. Excel Sink
    if request.sinks.excel:
        excel_bytes = ExcelExporter.export_to_bytes(dataset)
        _ARTIFACT_STORE[schema_id]["excel"] = {
            "bytes": excel_bytes,
            "filename": f"{schema_id}_data.xlsx",
            "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
        artifacts["excel"] = {
            "download_url": f"/api/v1/download/{schema_id}/excel",
            "sheets": dataset.execution_order
        }

    # 3. CSV Archive Sink
    if request.sinks.csv:
        csv_zip_bytes = CsvZipExporter.export_to_zip(dataset)
        _ARTIFACT_STORE[schema_id]["csv"] = {
            "bytes": csv_zip_bytes,
            "filename": f"{schema_id}_csv.zip",
            "media_type": "application/zip"
        }
        artifacts["csv"] = {
            "download_url": f"/api/v1/download/{schema_id}/csv"
        }

    # 4. Parquet Sink
    if request.sinks.parquet:
        parquet_tables = ParquetExporter.export_tables(dataset)
        # Package into a zip archive if multiple entities
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for ent_name, pq_bytes in parquet_tables.items():
                zf.writestr(f"{ent_name}.parquet", pq_bytes)
        pq_zip_bytes = zip_buf.getvalue()
        _ARTIFACT_STORE[schema_id]["parquet"] = {
            "bytes": pq_zip_bytes,
            "filename": f"{schema_id}_parquet.zip",
            "media_type": "application/zip"
        }
        artifacts["parquet"] = {
            "download_url": f"/api/v1/download/{schema_id}/parquet",
            "entities": list(parquet_tables.keys())
        }

    # 5. JSON Sink
    if request.sinks.json_export:
        json_bytes = JsonDocExporter.export_to_json(dataset)
        _ARTIFACT_STORE[schema_id]["json"] = {
            "bytes": json_bytes,
            "filename": f"{schema_id}_data.json",
            "media_type": "application/json"
        }
        artifacts["json"] = {
            "download_url": f"/api/v1/download/{schema_id}/json"
        }

    # 6. Dynamic Mock REST API Sink
    if request.sinks.api:
        DuckDBApiManager.persist_dataset(schema_id, dataset)
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


@app.get("/api/v1/mock/{schema_id}")
def get_mock_catalog(schema_id: str) -> Dict[str, Any]:
    """Catalog endpoint listing all entities and record counts for a schema."""
    try:
        return DuckDBApiManager.get_catalog(schema_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Schema '{schema_id}' not found in mock store: {str(e)}")


@app.get("/api/v1/mock/{schema_id}/{entity_name}")
def query_mock_entity(
    schema_id: str,
    entity_name: str,
    limit: int = Query(default=10, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
) -> Dict[str, Any]:
    """Dynamic mock REST endpoint with SQL pagination."""
    try:
        return DuckDBApiManager.query_paginated(
            schema_id=schema_id,
            entity_name=entity_name,
            limit=limit,
            offset=offset
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")


@app.get("/api/v1/download/{schema_id}/{export_type}")
def download_artifact(schema_id: str, export_type: str):
    """Downloads generated binary or text artifacts."""
    schema_artifacts = _ARTIFACT_STORE.get(schema_id)
    if not schema_artifacts or export_type not in schema_artifacts:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact '{export_type}' for schema '{schema_id}' not found."
        )

    item = schema_artifacts[export_type]
    return Response(
        content=item["bytes"],
        media_type=item["media_type"],
        headers={"Content-Disposition": f'attachment; filename="{item["filename"]}"'}
    )
