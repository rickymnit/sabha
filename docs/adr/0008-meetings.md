# ADR 0008: Meetings are analysed as a whole

- **Status:** Accepted
- **Date:** 2026-10-26
- **Plan task:** product owner's re-plan of 2026-10-24 (sales, meetings and company reception before infrastructure)

## Context

Every other conversation type analyses one staff member (teacher, receptionist, sales rep); the rest of the
speakers are context. A team meeting, such as a founder's weekly meeting, has no such person, and scoring
individual participants against each other would turn Sabha into a tool for ranking colleagues.

## Decision

Decided by the product owner on 2026-10-24.

1. **The meeting is scored, never a person.** The rubric (`rubrics/meeting.company.v0.1.yaml`) has one role,
   `participant`. The transcript step gives every voice that role (method `all_participants`), so there is nothing
   to guess and nothing to review. The prompts say the meeting is judged as a whole and never score, rank, praise or
   criticise an individual. The meeting's analysis and scores have no `person_id`, so they appear in nobody's
   trend; the recording keeps its organiser (who uploaded it) only for who may see it.
2. **Meeting notes come with the report** (`sabha_analytics.meetings`): decisions, action items (what, who as named
   in the meeting, the voice that took it when clear, and the date as said) and open questions. Every item rests on a
   quote verified like rubric evidence; unverified items are left out and counted.
3. **Voices, not people.** For meetings only, the model sees each line's anonymous voice label (S0, S1, ...) so it
   can say who took an action. Participation is measured in code as aggregates (`voice_count`, `top_voice_share`,
   `quiet_voice_count`); these metrics are never computed for lessons or calls, where counting voices would drift
   towards analysing students or callers (golden rule 10).
4. **Naming voices is display only.** Anyone who may see a meeting may name its voices (`PUT
   /v1/recordings/{id}/voices`, audited). Names are stored on the recording, shown in the transcript and the notes,
   and never sent to a model.

## Consequences

- Meetings are switched on for the company profile with the draft rubric; the demo company has them.
- Golden rule 10 is unchanged for lessons: voice labels and voice metrics stay out of every non-meeting analysis.
- Restart workers before the API when deploying (Recording gains `voice_names`; docs/runbook.md).
