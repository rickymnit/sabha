# eval

Quality evaluation on real, human-annotated data: gold-set manifests and transcripts, word error rate and speaker-role scoring (`wer.py`, `roles.py`), rater agreement (`kappa.py`), grounding checks, the LLM bake-off, and generated reports in `reports/`. Every quality number the product quotes must come from a script here run on the frozen gold set; nothing is estimated by hand.

## Comparing speech-to-text models (`asr_compare.py`, ADR 0012)

Sends the same audio pieces of calls already transcribed with Sarvam to other models, and writes a side-by-side HTML
report with cost, speed and how much each model differs from Sarvam. Sarvam is not asked again (its saved answer is
used), and every model's answers are cached in the report folder, so a second run costs nothing.

```bash
uv run python eval/asr_compare.py --tenant demo-company --models openai,qwen,aws --latest 5
uv run python eval/asr_compare.py --tenant demo-company --models openai:gpt-4o-mini-transcribe --recordings ID,ID
```

Keys come from `.env`: `OPENAI_API_KEY` (openai), `DASHSCOPE_API_KEY` (qwen), `AWS_TRANSCRIBE_BUCKET` plus AWS
credentials (aws). Self-hosted Whisper needs `uv sync --inexact --extra whisper`. `ASR_LANGUAGE=hi-IN` in front of the
command sends a Hindi hint to every model. The report goes to `eval/reports/asr-compare-<date>/index.html` and is not
committed (it holds transcripts).

"Differs from Sarvam" is not accuracy: nobody checked these transcripts by hand. Listen to the highlighted moments to
judge which model is right; word error rate comes only from `wer.py` on the gold set.
