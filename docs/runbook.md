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
