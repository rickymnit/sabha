# ADR 0007: How a recording leaves "Needs review"

- **Status:** Accepted
- **Date:** 2026-10-23
- **Plan task:** 6.7 (the needs-review half; disputes follow)

## Context

The pipeline stops a recording at NEEDS_REVIEW when it should not guess: the speakers' roles are unclear, no speech
or no words were found, too few scores could be checked against the transcript, the summary failed, or the
conversation type is uncertain. Until now nothing left NEEDS_REVIEW (`sabha_core/state.py`), so such a recording
stayed stuck and nobody could act on it in the app. Real classroom audio will hit "unclear roles" regularly (two
adults, a quiet teacher, group work).

## Decision

Decided by the product owner on 2026-10-23.

1. **Unclear roles: a reviewer says who the staff member is, and Sabha carries on.** The reviewer sees each speaker
   with their talk time, Sabha's best guess and a few sample lines with playback, and picks the teacher (or
   receptionist). That speaker gets the rubric's staff role and every other speaker the other role. The roles are
   stored on the recording (`confirmed_roles`) and it moves NEEDS_REVIEW -> TRANSCRIBING. The transcribe stage
   runs again: the speech recognition is reused from its checkpoints (no second provider call or charge), the
   transcript is rebuilt with the confirmed roles (method "reviewer"), and the recording goes on to analysis.
2. **Every other reason: explained, and the reviewer may only close it.** "Close: not usable" needs a note and moves
   NEEDS_REVIEW -> FAILED with reason `closed_by_reviewer`. Re-running analysis is not offered yet (each attempt
   costs an LLM call; it can be added as its own outcome later).
3. **Who decides.** Reviewers and managers for their units, owners and admins for everyone. Staff never resolve a
   review, not even of their own recording.
4. **Both outcomes are review transitions.** They are allowed only with `review=True` in the state machine (like
   re-analysis's `reanalysis=True`), so no other code path can move a recording out of NEEDS_REVIEW by accident.
   Each is one transaction with its outbox event and an `audit_log` entry (`recording.review`, with the decision,
   the roles or the note).

## Consequences

- `GET /v1/reviews`, `GET /v1/recordings/{id}/speakers` and `POST /v1/recordings/{id}/review` (in the permission
  matrix); the web app's Reviews page.
- Golden rule 5 still holds: a guess is never analysed. Analysis only runs on roles a person confirmed.
- Students' words appear in the speaker samples, as they already do in the transcript a manager can read. Students
  are still never scored or profiled (golden rule 10).
- Confirmed roles that no longer fit the transcript (a speaker missing, not exactly one staff member) send the
  recording back to review instead of being guessed around.
