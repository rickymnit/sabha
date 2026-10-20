"""Which tier each LLM task uses (plan task P5.1). The tier maps to a model in settings (LLM_MODEL_SMALL/_MID).

Task names are the constants the callers already use (sabha_analytics: TASK_CLASSIFY, TASK_SEGMENT,
TASK_SCORING, TASK_SYNTHESIS). A task not listed here is a configuration error, so usage and cost are always
reported per named task and the routing is reviewable in one place.
"""

from __future__ import annotations

from sabha_llm.types import Tier

TASK_TIERS: dict[str, Tier] = {
    "analysis.classify": "small",  # P5.8: conversation type and language mix
    "analysis.segment": "small",  # P5.8: lesson or call phases
    "roles.tiebreak": "small",  # P3.6: who is the teacher or receptionist, when heuristics disagree
    "analysis.scoring": "mid",  # P5.6: rubric dimensions with cited evidence
    "analysis.synthesis": "mid",  # P5.7: summary, coaching points, reception ticket
}
