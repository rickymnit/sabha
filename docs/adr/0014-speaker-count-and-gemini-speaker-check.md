# ADR 0014: Number of speakers and the Gemini speaker check, chosen at upload

- **Status:** Accepted
- **Date:** 2026-11-18 (model updated 2026-11-19)

## Context

On the Roshan sales call (NiaLabs demo, 2026-11-18) the opening, 0:06 to 0:33, was given to one speaker although
the customer and the sales rep take turns of a second or two. pyannote separates voices by sound alone; on a mono
phone line with two similar voices it merged them, and Deepgram's own speaker labels did the same. Running pyannote
on the full original audio instead of the speech-only audio did not help.

Gemini, given the audio and the transcript lines, also follows the conversation (a question and its answer are
said by different people) and got the opening right.

The owner decided on 2026-11-18:

1. Whoever uploads may say how many people speak in the recording.
2. Whoever uploads may ask for a Gemini check of who said each line, on top of pyannote.

## Decision

**Number of speakers** (`Recording.speaker_count`, 2 to 10, or automatic). The diarizer is asked for exactly that
many. Order: the uploader's number, then 3 for a support call a colleague helped on ([ADR 0015](0015-colleague-helped-calls.md)),
then the type's default (support calls: 2), otherwise pyannote decides. With 2 speakers, one is the staff member
and the other the customer.

**Speaker model** (`Recording.speaker_model`): `pyannote` (default) or `gemini` (pyannote plus the check).
The check, in `packages/asr/sabha_asr/speaker_check.py`, runs in the transcript step:

1. The words become lines: one speaker's words up to a sentence end or a change of speaker.
2. Gemini gets 3-minute windows of the **original** audio with the numbered lines heard in each. Line text is
   PII-masked first (golden rule 8). It answers with the numbers of the staff member's lines and the lines it
   cannot tell; the rest are the customer's.
3. A line of at least 3 words that Gemini gives to the other side moves there. Shorter lines ("ठीक", "ओके") and
   lines it cannot tell stay as pyannote had them. pyannote's turn times are kept; only whole lines move.

The result is stored as `speaker_check@v1.json` and on the transcript (`Transcript.speaker_check`: model, lines,
moved, unsure, cost). Its cost is added to the recording's speech-to-text cost.

**Model:** Gemini 3.8 Flash with thinking set to low (owner, 2026-11-19). On the Roshan call (12 minutes,
2026-11-18) it moved 39 to 40 of 264 lines over two runs, could not tell 1 to 6, got the opening right and cost ₹2.16 (about ₹10.8 per audio
hour). Gemini 3.1 Flash-Lite cost about ₹6.8 per hour but moved 25, could not tell 86 and left Roshan's own lines
with the customer. Gemini 2.5 Flash and 2.5 Flash-Lite are refused to our account (HTTP 404, "no longer available to
new users", 2026-11-18).

## Consequences

- If Gemini fails, the stage fails and is retried like speech-to-text. A transcript is never produced without a
  check that was asked for (golden rule 7).
- Audio goes to Google (outside India) under the speech-recognition residency exception of
  [ADR 0012](0012-more-asr-providers.md). Only send audio you have consent for.
- The 3-word minimum is a starting value, not measured. Whether the check improves speaker accuracy overall needs
  hand-labelled calls (`eval/roles.py`); one call is not a measurement.
- Gemini 3.8 Flash's input price doubles from 2027-01-01 (`sabha_asr/pricing.py`).
