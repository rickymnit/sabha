# Runbook

Operating notes for whoever deploys or runs Sabha. Add a section when something needs doing the same way twice.

## Deploying a change that adds a field to a stored document

The models in `packages/core/sabha_core/models.py` refuse fields they do not know (`extra="forbid"`), so a typo or a
stray field never slips into the database. The price: a process running older code cannot read a document written by
newer code. Seen on 2026-10-23 when `Recording.confirmed_roles` was added: the API (already updated) saved new
recordings with the field, the worker (still on the old code) failed to load them, and the uploads stayed at
UPLOADED.

So, when a release adds a field to a model:

1. Restart (or deploy) the **workers and the relay first**, then the API. New code reads old documents fine (the new
   field has a default); old code cannot read new ones.
2. If a recording got stuck meanwhile, it stays at its status with no stage running. The stuck-job sweeper
   (`make beat`) sends it again; locally, re-run the stage for it once the worker is updated.

Locally: `make api` reloads itself on every change but `make workers` and `make relay` do not, so restart them after
changing a model.

## Backups, restore drill, audio retention and erasure (P7.3)

**Backups.** Two copies:
1. Atlas continuous backup (turned on with the AWS setup in the last week; the cluster must be in Mumbai).
2. A nightly export by the worker's beat (`sabha.maintenance.backup`) to the backups bucket:
   `mongo/<YYYY-MM-DD>/<collection>.jsonl.gz` plus `manifest.json` (counts and SHA-256). `idempotency_keys` is left
   out (24-hour records). How long exports are kept is the backups bucket's lifecycle rule.

**Restore drill** (monthly, and after any change to the backup job):

    uv run python scripts/admin/restore_drill.py            # latest backup; prints PASSED or FAILED
    uv run python scripts/admin/restore_drill.py --day 2026-10-27 --keep   # keep restore_drill_20261027 to inspect

It restores into a scratch database named `restore_drill_*` (it refuses any other name, so it cannot touch the live
database), checks every collection's count against the manifest and a sample of documents against the file. Write
the date and result here:

| Date | Environment | Backup day | Result | By |
| --- | --- | --- | --- | --- |

**Audio retention.** Nightly (`sabha.maintenance.expire_audio`): audio older than the tenant's `retention_days` (90
by default) is deleted — the original and the working copies; transcripts, scores and reports stay. The report page
then says the audio was deleted. Before the first run on a new environment, and whenever in doubt:

    uv run python scripts/admin/expire_audio.py --dry-run

Change a customer's period with Sabha's admin tooling (owners see it read-only in Settings).

**Erasure on request.** The owner erases a recording (on its page) or a person with all their recordings and their
login (from People, the person's list): Sabha shows the count first and asks for the name. Activity keeps a
`data.erase` entry with the reason and counts. Whole-organisation erasure is not in the app; ask engineering.

**Backfill after an upgrade.** Fields added after recordings were processed (UI v2: the list rows' speaker strips,
speech time on recordings, reception tickets on analyses) are filled in from the files already in storage. It only
touches documents still missing them, so it is safe to run again. Run it once on each environment after deploying the UI v2 changes:

    uv run python scripts/admin/backfill.py --dry-run
    uv run python scripts/admin/backfill.py
