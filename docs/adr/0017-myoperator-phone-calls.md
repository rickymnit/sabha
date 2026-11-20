# ADR 0017: Phone calls from MyOperator

- **Status:** Accepted
- **Date:** 2026-11-20

## Context

NiaLabs takes its support and sales calls on MyOperator, which records every answered call. The manager asked for
those recordings to come into Sabha without anyone downloading and uploading files. MyOperator's API (Postman
collection "MyOperator API Document", checked 2026-11-20 against the live account) offers:

- Search Logs, `POST /search/search`: call logs newest first, with `from`/`to` in Unix seconds, `log_from` as the
  offset and at most 100 per page. Each log has the call id (`allcaller_id`), direction (`event` 1 incoming, 2
  outgoing), answered or missed (`status` 1 or 2), times, department, the customer's number, the recording's file
  name, and each leg's agent (`received_by`: user id, name, extension) with its `action` (received, missed,
  transferred).
- Recording link, `GET /recordings/link?file=`: a link to the MP3 (8 kHz mono, about 32 kbps), valid for 24 hours.
  The files are in an S3 bucket in `ap-south-1`, so the audio is stored in India.
- The token goes in the request as `token`, not in a header.

On 2026-11-20 the account had 659 calls in 7 days, and 1,663 answered, recorded calls in 30 days across 9 agents.

## Decision

Decided by the owner on 2026-11-20.

1. **Call details are copied in; audio only when asked.** A timed job (`sabha.phone_calls.sync`, every 10 minutes
   under `make beat`) copies answered, recorded calls into `phone_calls`, one document per call id. The first run
   goes back `MYOPERATOR_BACKFILL_DAYS` (30). The customer's number is kept as its last four digits only.
2. **Only the calls someone picks are analysed.** The Phone calls page has an Analyse button on every call. It makes
   a Recording (support or sales; `phone_call_id` links it to the call) and writes a `phone_call.import` event in the
   same transaction. The relay starts `sabha.phone_call_import`, which fetches a fresh link, downloads the MP3 into
   the audio bucket and moves the recording CREATED -> UPLOADED, so the pipeline runs as for an upload. The API never
   touches the audio (golden rule 2). If the download fails, the call says so and Analyse tries the same recording
   again.
3. **Consent:** every recording made from a call carries `MYOPERATOR_CONSENT_REF`, "MyOperator call-recording
   notice" (golden rule 9).
4. **Who:** owners and admins see every call; managers see the calls of people in their units; reviewers and staff
   do not see the page. Playing a call is audited as `phone_call.play`.
5. **Agents are matched to people once.** The first time one of an agent's calls is analysed, the person choosing
   says who the agent is in Sabha (owners and admins may add them as a new person in a unit). The match is kept on
   the person (`Person.phone_agent_ids`) and applied to all the agent's calls, which then also become visible to
   that unit's managers. A call with a second agent who answered is marked as one a colleague helped on (ADR 0015).
6. **One workspace, set in the environment.** `MYOPERATOR_API_TOKEN` and `MYOPERATOR_TENANT_ID` name the token and
   the workspace (NiaLabs, `demo-company`). Storing tokens per workspace in the database waits until a second
   customer needs it.
7. **Webhooks are not used.** MyOperator's webhooks need no authentication on our side, so anyone who found the
   address could send fake calls; reading calls with our own token is safer. A webhook could later trigger an early
   fetch.

## Consequences

- New: collection `phone_calls`, routes under `/v1/phone-calls` (in `docs/security/permissions.yaml`),
  `Person.phone_agent_ids`, `Recording.phone_call_id`. Restart the workers and relay before the API when deploying
  (docs/runbook.md).
- Audio is copied only for analysed calls, so storage grows with use, not with call volume. Speech-to-text and the
  LLM are paid per analysed call, as for uploads.
- MyOperator links expire after 24 hours, so playback always asks for a fresh one.
- Logs mask `token=` in URLs (sabha_core.logging), since MyOperator's token travels in the query string.
- API and webhook access needs MyOperator's SUV or Enterprise AI plan.
