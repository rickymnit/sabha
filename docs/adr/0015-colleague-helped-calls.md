# ADR 0015: Support calls a colleague helped on stay the first agent's

- **Status:** Accepted
- **Date:** 2026-11-19 (replaces the per-agent design of 2026-11-18)

## Context

In company support, an agent who cannot solve a problem sometimes hands the phone to a more experienced colleague
sitting beside them. One recording then holds three voices: the customer, the agent and the colleague.

On 2026-11-18 this was first built as a transfer between two agents, each to be scored on their own part. On
2026-11-19 the owner corrected it: the colleague only helps on the agent's phone. The call is technically the first
agent's, so every number, score and piece of coaching goes to them. Per-agent scoring was dropped for good.

## Decision

1. **Upload.** For support audio the upload page asks "Did a colleague help on this call?"
   (`Recording.transferred`). Anyone who uploads may say yes, staff included. Uploaders other than staff may also
   name the colleague under "Who helped (optional)" (`Recording.transfer_person_id`). Staff cannot name anyone
   (403); the colleague must be in a unit the uploader may see.
2. **Diarisation.** Exactly 3 speakers are asked for ([ADR 0014](0014-speaker-count-and-gemini-speaker-check.md)).
   On call 4 of the NiaLabs demo, 2 speakers merged the two agent voices; 3 separated them.
3. **Roles.** `sabha_asr/transfer.py` finds the customer and the two agent voices: the customer is heard
   throughout, while the agents split the call around a handover point. A voice needs 90% of its speech on one
   side of the handover to count as an agent. The rubric's evidence-based roles ([ADR 0011](0011-evidence-based-speaker-roles.md))
   can only block the result, when they say an "agent" voice sounds like the customer. Unclear results go to
   review, as before.
4. **Scoring.** Both agent voices get the staff role. Metrics are per role, so talk share, questions and pace
   count the two agents together, and the whole call is scored as the first agent's. `transfer@v1.json` and
   `Transcript.agents` keep which voice is which person (the colleague's only when named) and `handover_ms`.

## Consequences

- The report and the people pages show the call under the first agent only. The colleague gets no score from it.
- A colleague who talks a lot raises the agent side's talk share. That is accepted: the call is judged as the
  team's handling of the customer, credited to the agent who owns it.
- Support only. Sales calls, meetings and school recordings are unchanged.
