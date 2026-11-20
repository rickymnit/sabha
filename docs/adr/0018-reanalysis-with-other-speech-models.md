# ADR 0018: Re-analysis with other speech models, and model choice on Analyse

- **Status:** Accepted
- **Date:** 2026-11-20

## Context

Re-analysis (P2.8) only scored a finished recording again from its transcript. The owner wants to choose the speech
models when a phone call is analysed (ADR 0017) and when a conversation is re-analysed, and to compare the results.

## Decision

1. **Analyse on a phone call opens a window first:** analyse as support or sales, who the agent is (only when not
   linked yet), and the upload page's speech choices: transcription model (owners and admins), number of speakers,
   Standard or Standard + Gemini check, and for support calls whether a colleague helped (ticked when MyOperator shows
   two agents). The scoring model is shown, not chosen: one is set up.
2. **Re-analysing one conversation offers "Scores only" or "Transcribe again with other models".** The second goes
   COMPLETED -> DIARIZING when the number of speakers changes (confirmed roles and voice names are cleared, as the
   speaker labels change), otherwise COMPLETED -> TRANSCRIBING. Both transitions are allowed only with
   `reanalysis=True` and only for audio recordings whose audio is still kept. Owners and admins only, as before.
   Re-analysing several at once stays scores only.
3. **Runs, not overwrites.** `Recording.diarize_run` and `speech_run` number the runs like `analysis_run`; run n > 1
   writes to `diarize@v1-run<n>` / `transcribe@v1-run<n>` (golden rule 3). The transcribe stage reads the current
   diarize run, analysis the current transcribe run. Each run keeps its Transcript document (`run`); readers use the
   newest. The cost card adds the speech-to-text cost of every run, since each was paid for.

## Consequences

- A redo pays for speech-to-text again (and the Gemini check if chosen) and takes about as long as the first time.
  Changing only the speaker check still transcribes again.
- Earlier reports stay as earlier versions; open disputes are closed, as for any re-analysis.
- Restart workers and relay before the API when deploying (new Recording and Transcript fields; docs/runbook.md).
