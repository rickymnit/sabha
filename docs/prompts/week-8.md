# Week 8 — Pilot go-live and buffer

Goal: pilot schools use Sabha on real lessons and calls while we watch closely and fix fast.

---

## P8.8 · Go-live checklist and waves

```text
Create scripts/golive_check.py for a given tenant that verifies, and prints PASS/FAIL:
tenant exists with the school profile, plan and quota set; consent records present and valid for each unit;
coordinator and staff invited; at least one test upload processed end to end on production; alerts firing to
my phone (send a test alert); backup taken today; Sentry receiving events from prod; runbook URL reachable.
Also write docs/pilot/golive-plan.md: wave 1 (1 school, Monday), wave 2 (remaining schools, Wednesday),
rollback criteria (any data-isolation issue, consent issue, or > 10% failed jobs → pause the tenant).
```

Done when: wave 1 school passes the check and starts uploading.

---

## P8.9 · Daily pilot health report

```text
Create scripts/daily_report.py (runs each morning via beat, emails me): per tenant for the last 24 h —
uploads, completed, failed (with top error codes), needs review, median and p95 turnaround, GPU utilisation,
LLM cost per audio hour (from llm_calls), disputes opened, quota usage. Highlight anything outside SLO. Only
real measured numbers; show "no data" where empty.
```

Done when: the report arrives every morning during the pilot.

---

## P8.7 · Feedback log and dispute review

Plan task 8.7.

```text
Create a lightweight feedback system: feedback collection {tenant_id, source (call, whatsapp, in-app),
category (bug, accuracy, usability, request), severity, text, linked recording, status}; an in-app
"Send feedback" button on reports; an admin list with filters; a weekly export to docs/pilot/feedback-<week>.md
summarising themes, linked disputes and their resolutions, and candidate rubric changes (to evaluate on the
train split later, never applied directly).
```

Done when: every pilot call or message ends up as a logged item.

---

## Hotfix template

```text
/fix <paste the error, logs, recording id and what the user saw>
Production rule: smallest safe change, test first, deploy with scripts/deploy_prod.sh, verify on the affected
recording, and add a runbook note if it could recur.
```

## Retro template

```text
Read eval/reports/, docs/pilot/feedback-*.md, the DLQ history and the daily reports for the pilot. Write
docs/pilot/retro.md: what worked, what broke (with counts), quality results vs gates, cost per audio hour
measured, top 10 user requests, and a ranked post-pilot backlog using the plan's "After the pilot" list as the
starting point. Use only data from these files; mark anything unknown.
```
