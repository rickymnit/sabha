"""The unit tree (units form a tree through parent_id): a unit and everything under it. Used for access (a manager of
"Class 6" also manages its sections) and for narrowing numbers to one unit."""

from __future__ import annotations

from collections.abc import Iterable

from sabha_core.models import Unit


def subtree(units: Iterable[Unit], unit_ids: Iterable[str]) -> set[str]:
    """The given units and every unit under them, at any depth (a circular parent chain is walked once). Ids that
    are not units are kept as they are, so an access list never loses an entry."""
    children: dict[str, list[str]] = {}
    for u in units:
        if u.parent_id:
            children.setdefault(u.parent_id, []).append(u.id)
    found = set(unit_ids)
    todo = list(found)
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found
