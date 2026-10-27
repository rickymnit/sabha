"""GET /v1/search: the header search (UI v2), by name only (owner's decision, 2026-10-27): people by name and
recordings by file name, a few of each, from what the caller may see. Not transcripts: searching "anything said"
would need a text index on the transcripts and is not built.

The text is matched as a case-insensitive substring; it is escaped, so it is never read as a pattern. Every query
is AND-ed with the same visibility rules as GET /v1/people and GET /v1/recordings, so search never shows more.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from sabha_api.auth import Principal
from sabha_api.services.results import PersonOut, RecordingOut, people_filter, recording_out, visible_filter
from sabha_core.models import Analysis, Person, Recording, Transcript
from sabha_core.repo import TenantRepo

MIN_LENGTH = 2
MAX_LENGTH = 100
LIMIT = 5


class SearchOut(BaseModel):
    people: list[PersonOut]
    recordings: list[RecordingOut]  # newest first


async def search(
    principal: Principal, q: str, *, people: TenantRepo[Person], recordings: TenantRepo[Recording],
    analyses: TenantRepo[Analysis], transcripts: TenantRepo[Transcript],
) -> SearchOut:  # fmt: skip
    pattern = {"$regex": re.escape(q.strip()), "$options": "i"}
    found_people = await people.find({"$and": [people_filter(principal), {"name": pattern}]}, sort=[("name", 1)],
                                     limit=LIMIT)  # fmt: skip
    visible = await visible_filter(principal, people)
    found = await recordings.find({"$and": [visible, {"file_name": pattern}]},
                                  sort=[("created_at", -1), ("_id", -1)], limit=LIMIT)  # fmt: skip
    return SearchOut(
        people=[PersonOut(id=p.id, name=p.name, unit_id=p.unit_id) for p in found_people],
        recordings=await recording_out(found, people, analyses, transcripts),
    )
