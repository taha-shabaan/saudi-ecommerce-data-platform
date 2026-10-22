"""
Relational Synthetic Data Engine with Batch Generation,
Row-Level Locale Binding, In-Memory PK Pool, and Anomaly Injection.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import time
import random
from app.models.schema import GenerateRequest, EntityDefinition, AttributeDefinition
from app.core.resolver import resolve_execution_order, ExecutionPlan
from app.core.registry import GeneratorRegistry, GeneratorContext


LOCALE_COUNTRY_MAP = {
    "ar_EG": "Egypt",
    "en_US": "United States",
    "de_DE": "Germany",
    "fr_FR": "France",
    "ar_SA": "Saudi Arabia",
    "ur_PK": "Pakistan",
    "es_ES": "Spain",
    "it_IT": "Italy",
    "ja_JP": "Japan"
}


@dataclass
class GeneratedDataset:
    """Contains in-memory generated records, metadata, and execution statistics."""
    success: bool
    records: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)
    pk_pools: Dict[str, List[Any]] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class DataEngine:
    """Core synthetic data generation orchestrator."""

    def __init__(self, batch_size: int = 2000):
        self.batch_size = batch_size

    def generate(self, request: GenerateRequest) -> GeneratedDataset:
        """
        Executes topological sorting and chunked batch generation
        while maintaining referential integrity across entities.
        """
        start_time = time.perf_counter()
        warnings: List[str] = []

        # 1. Resolve execution order
        plan: ExecutionPlan = resolve_execution_order(request.entities)
        entity_map: Dict[str, EntityDefinition] = {e.name: e for e in request.entities}

        records_by_entity: Dict[str, List[Dict[str, Any]]] = {}
        pk_pools: Dict[str, List[Any]] = {}

        # 2. Iterate through entities in topological order
        for entity_name in plan.execution_order:
            entity = entity_map[entity_name]
            entity_records: List[Dict[str, Any]] = []
            
            # Initialize PK pools for this entity's primary keys
            for attr in entity.attributes:
                if attr.is_primary_key:
                    pk_pools[f"{entity.name}.{attr.name}"] = []

            is_self_ref = entity_name in plan.self_referential_entities

            # Batch iteration
            total_records = entity.record_count
            for row_idx in range(total_records):
                # Row-Level Locale Binding
                base_locale = random.choice(request.locales) if request.locales else "en_US"

                record: Dict[str, Any] = {}

                for attr in entity.attributes:
                    # Check nullability
                    if attr.nullable and random.random() < attr.null_probability:
                        record[attr.name] = None
                        continue

                    # Handle Foreign Key attribute
                    if attr.type == "foreign_key" and attr.fk_target:
                        val = self._resolve_foreign_key(
                            attr=attr,
                            entity=entity,
                            row_idx=row_idx,
                            pk_pools=pk_pools,
                            orphan_rate=request.policy.orphan_rate,
                            is_self_ref=is_self_ref,
                            warnings=warnings
                        )
                    else:
                        # Determine active locale (check locale drift)
                        active_locale = base_locale
                        if (
                            request.policy.locale_drift_rate > 0.0
                            and random.random() < request.policy.locale_drift_rate
                        ):
                            active_locale = random.choice(request.locales)

                        # Enforce consistent country naming if generator is country
                        if attr.type == "country" and active_locale in LOCALE_COUNTRY_MAP:
                            val = LOCALE_COUNTRY_MAP[active_locale]
                        else:
                            ctx = GeneratorContext(
                                locale=active_locale,
                                row_index=row_idx,
                                params=attr.params,
                                noise_rate=request.policy.noise_rate,
                                current_record=record,
                                pk_pools=pk_pools
                            )
                            val = GeneratorRegistry.generate(attr.type, ctx)

                    record[attr.name] = val

                    # Record primary key in pool
                    if attr.is_primary_key:
                        pk_pools[f"{entity.name}.{attr.name}"].append(val)

                # Check Duplicate Injection
                if (
                    request.policy.duplicate_rate > 0.0
                    and entity_records
                    and random.random() < request.policy.duplicate_rate
                ):
                    # Clone previous record
                    entity_records.append(dict(entity_records[-1]))
                else:
                    entity_records.append(record)

            records_by_entity[entity_name] = entity_records

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        total_rows = sum(len(rows) for rows in records_by_entity.values())

        metrics = {
            "duration_ms": duration_ms,
            "total_entities": len(plan.execution_order),
            "total_records": total_rows,
            "entity_record_counts": {k: len(v) for k, v in records_by_entity.items()}
        }

        return GeneratedDataset(
            success=True,
            records=records_by_entity,
            execution_order=plan.execution_order,
            pk_pools=pk_pools,
            metrics=metrics,
            warnings=warnings
        )

    def _resolve_foreign_key(
        self,
        attr: AttributeDefinition,
        entity: EntityDefinition,
        row_idx: int,
        pk_pools: Dict[str, List[Any]],
        orphan_rate: float,
        is_self_ref: bool,
        warnings: List[str]
    ) -> Any:
        """Samples parent primary keys with orphan injection & self-referential support."""
        # 1. Orphan Key Injection
        if orphan_rate > 0.0 and random.random() < orphan_rate:
            return 999000 + random.randint(1, 9999)

        target = attr.fk_target or ""
        pool = pk_pools.get(target, [])

        # Self-referential special handling (first row has no parent ID, subsequent rows sample from emitted IDs)
        if is_self_ref and target.startswith(f"{entity.name}."):
            if not pool:
                return None
            return random.choice(pool)

        if not pool:
            warnings.append(f"Foreign key target pool '{target}' was empty when generating '{entity.name}.{attr.name}'.")
            return None

        # Standard 1-to-many uniform sampling
        return random.choice(pool)
