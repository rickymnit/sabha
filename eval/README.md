# eval

Quality evaluation on real, human-annotated data: gold-set manifests and transcripts, word error rate and speaker-role scoring (`wer.py`, `roles.py`), rater agreement (`kappa.py`), grounding checks, the LLM bake-off, and generated reports in `reports/`. Every quality number the product quotes must come from a script here run on the frozen gold set; nothing is estimated by hand.
