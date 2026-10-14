# packages/analytics

`sabha_analytics`, which turns transcripts into feedback: it loads rubric files, computes metrics in code (talk share, question counts, pace, silence, monologue length), asks the LLM only for judgements, verifies every quoted piece of evidence against the transcript, and assembles the report. Unverified output is never shown to users.
