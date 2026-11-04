# ADR 0011: Evidence-based speaker roles for support calls

- **Status:** Accepted
- **Date:** 2026-11-04
- **Amends:** the role rules of plan task P3.6 (`sabha_asr.roles`) for conversation types with an evidence profile

## Context

Support calls swapped agent and customer. On one call nobody said the company's name, so the greeting rule had no
evidence, and the AI tie-breaker read a garbled opening and named the customer as the agent with 89% confidence,
which Sabha accepted (its bar was 70%). On a support call, the agent is not the one who speaks first or explains
the problem: a customer often calls, talks most and explains at length.

## Decision

Decided by the product owner on 2026-11-04. Support calls always have exactly one agent and one customer.

1. **Evidence profiles per conversation type** (`sabha_asr.role_evidence`), support first. A profile lists
   behaviours (cues) pointing to the staff member or to the other side, with weights. Support: greets and names
   the organisation (+4, opening only), introduces as support (+3), asks for the AnyDesk ID (+3), guides software
   steps (+3), explains a module (+3), asks which school (+2) and more for the agent; introduces as a school
   representative (+3), describes a problem (+3), reads out the AnyDesk ID (+3) or a long number (+2), asks how to
   (+2) and more for the customer. Speaking first is +0.5. The weights are starting values, not measurements.
2. **Whole conversation.** A cue counts at most once per speaker; greetings count only in the first 30 s, the rest
   over the whole call. The first two minutes are weighed on their own too, and must not point to the other speaker.
3. **Both hypotheses.** "A is the agent" collects A's agent cues and B's customer cues, and the reverse. Confidence
   is 0.5 + 0.5 x margin x strength. Strong (>= 0.9) or corroborated (>= 0.75 with two different cues) evidence
   decides. Conflicting evidence (both sides strong, or the first minutes disagreeing) goes straight to a reviewer.
   Anything else goes to the AI.
4. **The AI as a tie-breaker only.** It is told what support calls look like and who the agent works for, reads the
   first five minutes, and must return quotes for both sides, each with its speaker. Quotes not found in what that
   speaker said are dropped; without one on each side, or if it asks for review, its answer is not used. On support
   calls it must be at least 90% sure and must not contradict the evidence's lean (confidence >= 0.6).
5. **Reviewer corrections are kept for measurement.** The automatic decision is saved in `roles_auto@v1.json` and
   the evidence in `role_evidence@v1.json`, never overwritten by a reviewer's confirmation;
   `eval/role_corrections.py` lists every correction against them.

Other types keep their rules until they get a profile.

## Consequences

- More support calls go to review at first: when the evidence is thin or contradictory, a person decides instead
  of the AI guessing. The review screen already asks "which speaker is the agent?".
- Cue phrases are Hindi and English as Sarvam writes them. Calls in other languages find few cues and go to the AI
  or a reviewer until the profile has phrases for them.
- The weights and thresholds must be calibrated on reviewer corrections and the gold set (`eval/roles.py`) before
  they are trusted; no accuracy is claimed here.
