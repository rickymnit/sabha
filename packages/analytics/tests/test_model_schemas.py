"""Every answer format we send to the model must be one OpenAI's strict structured outputs accept (checked live on
2026-10-26, when `oneOf` in the deal card and the reception ticket was refused with HTTP 400 invalid_json_schema):

- no `oneOf` (use `anyOf`);
- every object closes with additionalProperties false and lists all of its properties as required.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from sabha_analytics.classify import classification_schema
from sabha_analytics.phases import DEFAULT_PHASES, phases_schema
from sabha_analytics.reception import TicketValues, ticket_schema
from sabha_analytics.rubric import Rubric
from sabha_analytics.sales import deal_card_schema
from sabha_analytics.scoring import scoring_output_schema
from sabha_analytics.synthesis import Moment, synthesis_output_schema


def nodes(schema: Any, path: str = "$") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(schema, dict):
        yield path, schema
        for key, value in schema.items():
            yield from nodes(value, f"{path}.{key}")
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            yield from nodes(value, f"{path}[{i}]")


def schemas(rubric: Rubric) -> dict[str, dict[str, Any]]:
    moment = Moment("u0001", "teacher", 0, 1_000, "Aaj hum fractions padhenge")
    return {
        "scoring": scoring_output_schema(rubric.dimensions),
        "synthesis": synthesis_output_schema([moment]),
        "classify": classification_schema(["teaching", "reception"]),
        "phases": phases_schema(DEFAULT_PHASES["sales"]),
        "ticket": ticket_schema(TicketValues(("fee_query", "other"), ("resolved", "follow_up_needed"))),
        "deal card": deal_card_schema(("high", "medium", "low", "unclear")),
    }


@pytest.mark.parametrize("name", ["scoring", "synthesis", "classify", "phases", "ticket", "deal card"])
def test_answer_formats_are_accepted_by_strict_structured_outputs(rubric: Rubric, name: str) -> None:
    problems = []
    for path, node in nodes(schemas(rubric)[name]):
        if "oneOf" in node:
            problems.append(f"{path}: oneOf (use anyOf)")
        if node.get("type") == "object" and "properties" in node:
            if node.get("additionalProperties") is not False:
                problems.append(f"{path}: additionalProperties must be false")
            if set(node.get("required", [])) != set(node["properties"]):
                problems.append(f"{path}: every property must be required")
    assert problems == []
