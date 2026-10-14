Run the quality-gate checks and write a report to eval/reports/gate-$ARGUMENTS-<date>.md (argument is 1, 2 or 3).

Gate 1: run `make eval-wer` and `uv run python eval/roles.py`; report WER per language mix and room type, role accuracy, real-time factor and cost per audio hour from the latest pipeline metrics. Compare against the targets in eval/targets.yaml.
Gate 2: run `make eval-kappa` and `uv run python eval/grounding.py` on the HOLD-OUT split only; report kappa per dimension per rubric, grounding pass rate, number of real reports per conversation type, LLM cost per audio hour.
Gate 3: run the checklist in docs/gate3-checklist.md: load-test results file, chaos-test results, security scan output, tenant-isolation test run, last backup-restore rehearsal, legal sign-off and consent records (ask me for these), on-call rota and runbook presence.

Never estimate or invent a number. If an input is missing, write MISSING and what is needed. End with PASS / FAIL per criterion and an overall verdict.
