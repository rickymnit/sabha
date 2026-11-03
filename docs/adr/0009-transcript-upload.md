# ADR 0009: Meeting transcripts can be uploaded instead of audio

- **Status:** Accepted
- **Date:** 2026-11-02
- **Plan task:** product owner's request of 2026-11-02 (sales calls held on Google Meet)

## Context

Many conversations, sales demos especially, now happen on Google Meet, which writes its own transcript. When that
transcript exists, cleaning the audio, separating the speakers and speech-to-text are slow and paid work that the
meeting tool has already done, and its speaker names are more reliable than voice clustering. The audio is often
not kept at all. Users asked to upload the transcript when there is one, and the audio when there is not.

A Meet transcript (.txt) has `Name: text` lines and a time marker about once a minute, not one per line. Some
exports label speakers "Speaker 1", "Speaker 2" instead of names.

## Decision

Decided by the product owner on 2026-11-02.

1. **One upload, two kinds of file.** The upload page and `POST /v1/recordings` take a `.txt` (text/plain, at most
   5 MB) next to the audio formats. The recording gets `source: "transcript"` (otherwise `"audio"`). Everything
   else is unchanged: the same direct-to-storage upload (the API never reads the file), the same consent rule
   (golden rule 9), the same rubrics, review and results.
2. **One guarded shortcut in the state machine.** An imported transcript goes `UPLOADED -> TRANSCRIBING`, allowed
   only with `imported=True` *and* only when the stored recording's `source` is `"transcript"`, checked in the same
   conditional update. An audio recording can never skip its stages. Retries, review (`NEEDS_REVIEW ->
   TRANSCRIBING`) and re-analysis work as before.
3. **The transcribe stage reads the file** (`sabha_workers.stages.imported`, reader in `sabha_asr.imported`), then
   hands words and turns to the same roles and transcript step as speech recognition. Finding the sales rep (or
   receptionist, or teacher) uses the existing heuristics, the LLM tie-breaker and a reviewer, so "Speaker 1/2"
   files need nothing extra.
4. **Times are estimates, and say so.** Lines between two markers share that stretch in proportion to their length;
   the transcript is stored with `word_timing: "approximate"` and the results page says times are approximate, to
   about a minute. The text is exactly the file's, so quotes are verified against it as for audio (golden rule 5).
   A file with no time markers is refused (`no_timestamps`): every judgement must cite a time.
5. **No invented numbers.** A transcript says nothing about silence, so the silence metrics are left out for it
   rather than shown as zero. Talk share and monologue length come from the estimated times.
6. **Names stay out of models.** Speakers become S1, S2, ...; the names in the file are kept on the recording as
   `voice_names` for display only. A name spoken aloud in the conversation stays in the text, as with audio.
7. **Meeting time.** When the uploader gives no time, the start time in Meet's file name ("2026_11_02 11_18 IST")
   is stored as `recorded_at`.

## Consequences

- No speech provider is called and nothing is billed for speech on these recordings.
- There is no audio to play; evidence links jump to the transcript line instead.
- Only Google Meet's .txt layout is read so far. Word (.docx) exports and other tools (Zoom and Teams .vtt) can be
  added as further readers in `sabha_asr.imported` without changing the pipeline.
