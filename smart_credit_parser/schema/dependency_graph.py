"""
Dependency graph computation and topological sort for canonical database schema.
Ensures correct insertion order respecting foreign keys.
"""

from typing import Dict, List, Set
from .models import TableSchema


def compute_topological_order(tables: Dict[str, TableSchema]) -> List[str]:
    """
    Computes a valid insertion order for tables using Kahn's algorithm or DFS.
    Tables with no foreign key dependencies are placed first.
    """
    # Graph: table -> set of tables it depends on (incoming edges)
    dependencies: Dict[str, Set[str]] = {t_name: set() for t_name in tables}

    for t_name, tbl in tables.items():
        for fk in tbl.foreign_keys:
            ref_table = fk.referenced_table.lower()
            # Ignore self-references or missing tables
            if ref_table in dependencies and ref_table != t_name.lower():
                dependencies[t_name].add(ref_table)

    # Kahn's algorithm
    order: List[str] = []
    # Find tables with no dependencies
    ready = [t for t, deps in dependencies.items() if len(deps) == 0]

    # Deterministic sorting for stability
    ready.sort()

    while ready:
        node = ready.pop(0)
        order.append(node)

        # For every other table that depended on this node, remove the dependency
        for t, deps in dependencies.items():
            if node in deps:
                deps.remove(node)
                if len(deps) == 0 and t not in order and t not in ready:
                    ready.append(t)
        ready.sort()

    # If circular dependencies remain, append remaining tables
    for t in tables:
        if t not in order:
            order.append(t)

    return order
