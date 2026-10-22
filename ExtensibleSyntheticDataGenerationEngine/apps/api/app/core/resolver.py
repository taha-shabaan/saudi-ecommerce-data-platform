"""
Topological Dependency Graph Resolver using NetworkX.
Determines valid entity generation order and detects circular foreign key relationships.
"""

from typing import List, Set, Dict
from dataclasses import dataclass, field
import networkx as nx
from app.models.schema import EntityDefinition


class ResolverError(Exception):
    """Base exception for dependency resolution errors."""
    pass


class CircularDependencyError(ResolverError):
    """Raised when an unresolvable cycle exists between entities."""
    pass


class MissingEntityReferenceError(ResolverError):
    """Raised when a foreign key references a non-existent entity."""
    pass


@dataclass
class ExecutionPlan:
    """Represents a topologically sorted entity execution plan."""
    is_valid: bool
    execution_order: List[str]
    self_referential_entities: Set[str] = field(default_factory=set)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)


def resolve_execution_order(entities: List[EntityDefinition]) -> ExecutionPlan:
    """
    Constructs a directed graph of foreign key dependencies and resolves
    the topological generation sequence.

    Args:
        entities: List of EntityDefinition models.

    Returns:
        ExecutionPlan with execution order and self-referential markers.

    Raises:
        MissingEntityReferenceError: If a foreign key points to a non-existent entity.
        CircularDependencyError: If a cycle exists between entities.
    """
    graph = nx.DiGraph()
    entity_names = {e.name for e in entities}
    self_referential: Set[str] = set()

    # Add all entity nodes to graph
    for entity in entities:
        graph.add_node(entity.name)

    # Add directed edges: parent -> child (parent must generate before child)
    for entity in entities:
        for attr in entity.attributes:
            if attr.type == "foreign_key" and attr.fk_target:
                parts = attr.fk_target.split(".")
                parent_entity = parts[0]

                if parent_entity not in entity_names:
                    raise MissingEntityReferenceError(
                        f"Entity '{parent_entity}' referenced by '{entity.name}.{attr.name}' not found in schema."
                    )

                if parent_entity == entity.name:
                    # Intra-entity self-reference (e.g. employees.manager_id -> employees.id)
                    # Handled via sequential two-pass generation, not an inter-entity DAG cycle
                    self_referential.add(entity.name)
                else:
                    # Directed edge: parent must exist before child can sample its PKs
                    graph.add_edge(parent_entity, entity.name)

    # Check for cycles
    if not nx.is_directed_acyclic_graph(graph):
        cycles = list(nx.simple_cycles(graph))
        cycle_paths = []
        for cycle in cycles:
            path = " ➔ ".join(cycle + [cycle[0]])
            cycle_paths.append(path)
        
        cycle_str = "; ".join(cycle_paths)
        raise CircularDependencyError(
            f"Circular dependency detected among entities: [{cycle_str}]. Generation cannot proceed."
        )

    # Compute topological order
    order = list(nx.topological_sort(graph))

    # Track direct parent dependencies for each entity
    dependencies: Dict[str, List[str]] = {
        name: list(graph.predecessors(name)) for name in entity_names
    }

    return ExecutionPlan(
        is_valid=True,
        execution_order=order,
        self_referential_entities=self_referential,
        dependencies=dependencies
    )
