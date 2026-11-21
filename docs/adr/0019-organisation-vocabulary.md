# ADR 0019: The organisation's words in speech-to-text

Date: 2026-11-21. Status: accepted.

## Context

Speech-to-text does not know a company's own words. On Schoollog ERP calls "Schoollog" comes back as "schoolo",
"schoollo" or "school log", and "ERP" as "arp". Wrong words make transcripts hard to read, break role detection
(the company name is how a greeting is recognised) and make coaching quote the agent wrongly.

## Decision

Each tenant has a word list, `Tenant.vocabulary`: terms (as they are written) with the wrong spellings heard so far
(`sounds_like`). Owners and admins edit it in Settings, "Words Sabha should know" (PATCH /v1/settings, audited as
settings.update; no new route).

1. **Hints.** The transcribe stage gives the terms (at most 50) to the speech model on every chunk
   (`AudioChunk.hints`): Deepgram Nova-3 `keyterm`, the OpenAI and Groq `prompt`, and a line at the end of Gemini's
   instruction. Sarvam, Qwen, AWS and local Whisper get no hints.
2. **Fixes.** After the chunks are merged, `sabha_asr.vocabulary.fix_words` replaces each wrong spelling with its term,
   for every provider: whole words only, ignoring case and punctuation, longest spelling first, up to 5 words per
   spelling ("school log" -> "Schoollog"; "sharp" is not touched by "arp"). The term in another case is put in the
   term's case. The term's words share the replaced words' time; confidence is the lowest of them. The count is
   `vocabulary_fixes` in asr@v1.json and the stage log.

Roles, the transcript, grounding and scoring all read the fixed words, so quotes are checked against what users see.

## Consequences

- Only conversations transcribed after a change use it; earlier ones change when re-analysed.
- A wrong spelling that is also a real word in the calls (for example "tally" as a verb) would be replaced; keep the
  list to spellings that only mean the term.
- The original provider words are not kept beside the fixed ones; the per-chunk provider output (`parts`) still is.
