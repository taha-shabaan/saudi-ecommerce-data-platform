"""
Tests for Seam 1: Topological DAG Dependency Resolver (NetworkX)
"""

import pytest
from app.models.schema import EntityDefinition, AttributeDefinition
from app.core.resolver import resolve_execution_order, CircularDependencyError, MissingEntityReferenceError


def test_linear_dependency_order():
    """
    Test standard linear relational chain:
    users -> orders -> order_items
    """
    entities = [
        EntityDefinition(
            name="orders",
            record_count=10,
            attributes=[
                AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                AttributeDefinition(name="user_id", type="foreign_key", fk_target="users.id"),
            ]
        ),
        EntityDefinition(
            name="order_items",
            record_count=20,
            attributes=[
                AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                AttributeDefinition(name="order_id", type="foreign_key", fk_target="orders.id"),
            ]
        ),
        EntityDefinition(
            name="users",
            record_count=5,
            attributes=[
                AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                AttributeDefinition(name="name", type="full_name"),
            ]
        ),
    ]

    plan = resolve_execution_order(entities)
    assert plan.is_valid is True
    # users must generate before orders, and orders before order_items
    assert plan.execution_order.index("users") < plan.execution_order.index("orders")
    assert plan.execution_order.index("orders") < plan.execution_order.index("order_items")


def test_circular_dependency_raises_error():
    """
    Test cycle detection:
    table_a -> table_b -> table_a
    Must raise CircularDependencyError with diagnostic path.
    """
    entities = [
        EntityDefinition(
            name="table_a",
            record_count=5,
            attributes=[
                AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                AttributeDefinition(name="b_id", type="foreign_key", fk_target="table_b.id"),
            ]
        ),
        EntityDefinition(
            name="table_b",
            record_count=5,
            attributes=[
                AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                AttributeDefinition(name="a_id", type="foreign_key", fk_target="table_a.id"),
            ]
        ),
    ]

    with pytest.raises(CircularDependencyError) as exc_info:
        resolve_execution_order(entities)
    
    msg = str(exc_info.value)
    assert "Circular dependency detected" in msg
    assert "table_a" in msg
    assert "table_b" in msg


def test_self_referential_key_is_allowed():
    """
    Test self-referencing relationship:
    employees.manager_id -> employees.id
    This should NOT trigger a circular dependency error.
    """
    entities = [
        EntityDefinition(
            name="employees",
            record_count=10,
            attributes=[
                AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                AttributeDefinition(name="name", type="full_name"),
                AttributeDefinition(name="manager_id", type="foreign_key", fk_target="employees.id", nullable=True),
            ]
        )
    ]

    plan = resolve_execution_order(entities)
    assert plan.is_valid is True
    assert plan.execution_order == ["employees"]
    assert "employees" in plan.self_referential_entities


def test_missing_parent_entity_raises_error():
    """
    Test referencing an entity that does not exist in schema.
    """
    entities = [
        EntityDefinition(
            name="orders",
            record_count=5,
            attributes=[
                AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                AttributeDefinition(name="customer_id", type="foreign_key", fk_target="customers.id"),
            ]
        )
    ]

    with pytest.raises(MissingEntityReferenceError) as exc_info:
        resolve_execution_order(entities)
    
    assert "Entity 'customers' referenced by 'orders.customer_id' not found in schema" in str(exc_info.value)
