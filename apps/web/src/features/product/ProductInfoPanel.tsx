// Approved product information on the Settings page (founder's Sales Executive dashboard doc, 2026-11-12): owners
// and admins add, edit and retire the entries that AI coaching may use for product facts. Nobody else edits them.

import { useId, useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { useProductInfo, useProductInfoChanges } from "../../api/hooks";
import type { ProductInfoItem } from "../../api/types";
import { Button, Input, Panel, useToast } from "../../design";

const BODY_MAX = 3000;

function EntryForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: { title: string; body: string };
  submitLabel: string;
  onSubmit: (value: { title: string; body: string }) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const bodyId = useId();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const ready = title.trim() !== "" && body.trim() !== "";
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(undefined);
    try {
      await onSubmit({ title: title.trim(), body: body.trim() });
      if (!initial) {
        setTitle("");
        setBody("");
      }
      onCancel?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not save. Please try again.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
      <Input
        label="Topic"
        placeholder="For example: Pricing and billing"
        value={title}
        maxLength={120}
        onChange={(e) => setTitle(e.target.value)}
      />
      <div className="flex flex-col gap-1.5">
        <label htmlFor={bodyId} className="text-sm font-semibold text-ink">
          Approved information
        </label>
        <textarea
          id={bodyId}
          value={body}
          rows={4}
          onChange={(e) => setBody(e.target.value.slice(0, BODY_MAX))}
          placeholder="What the team may tell clients about this topic, in plain words."
          className="rounded-card border border-line-input bg-surface p-3 text-ink"
        />
        <span className="text-caption text-muted">
          {body.length} / {BODY_MAX}
        </span>
      </div>
      {error && <p className="m-0 text-small text-danger">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="secondary" disabled={busy || !ready}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

function Entry({ entry }: { entry: ProductInfoItem }) {
  const { change } = useProductInfoChanges();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const retired = entry.status === "retired";
  const setStatus = async (status: "active" | "retired") => {
    try {
      await change.mutateAsync({ id: entry.id, status });
      toast.show({ tone: "success", title: status === "retired" ? "Retired" : "Back in use" });
    } catch (e) {
      toast.show({ tone: "error", title: e instanceof ApiError ? e.message : "That did not save." });
    }
  };
  if (editing) {
    return (
      <li className="border-b border-line-subtle py-4 last:border-b-0">
        <EntryForm
          initial={{ title: entry.title, body: entry.body }}
          submitLabel="Save"
          onSubmit={(value) => change.mutateAsync({ id: entry.id, ...value })}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 border-b border-line-subtle py-4 last:border-b-0">
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-1">
        <span className="font-semibold text-ink">
          {entry.title}
          {retired && <span className="ml-2 rounded-full bg-fill px-2 py-0.5 text-caption text-muted">Retired</span>}
        </span>
        <span className="whitespace-pre-line text-sm text-ink-2">{entry.body}</span>
      </div>
      <div className="flex shrink-0 gap-2">
        {!retired && (
          <Button variant="ghost" onClick={() => setEditing(true)}>
            Edit
          </Button>
        )}
        <Button variant="ghost" onClick={() => void setStatus(retired ? "active" : "retired")}>
          {retired ? "Use again" : "Retire"}
        </Button>
      </div>
    </li>
  );
}

export function ProductInfoPanel() {
  const list = useProductInfo(true);
  const { add } = useProductInfoChanges();
  const [adding, setAdding] = useState(false);
  const items = list.data?.items ?? [];
  const active = items.filter((i) => i.status === "active");
  const retired = items.filter((i) => i.status === "retired");
  return (
    <Panel
      title="Approved product information"
      description="AI coaching uses only this information when it talks about your products, and points your team to the right topic to review. Only owners and administrators can change it."
      className="gap-2"
    >
      {list.isError ? (
        <p className="m-0 text-muted">The product information could not be loaded. Please try again in a moment.</p>
      ) : list.isPending ? (
        <p className="m-0 text-muted">Loading…</p>
      ) : (
        <>
          {active.length === 0 && !adding && (
            <p className="m-0 text-muted">
              Nothing added yet. Until you add something, coaching gives no product facts.
            </p>
          )}
          <ul className="m-0 flex list-none flex-col p-0">
            {active.map((entry) => (
              <Entry key={entry.id} entry={entry} />
            ))}
          </ul>
          {adding ? (
            <div className="rounded-card border border-line-subtle p-4">
              <EntryForm
                submitLabel="Add"
                onSubmit={(value) => add.mutateAsync(value)}
                onCancel={() => setAdding(false)}
              />
            </div>
          ) : (
            <div>
              <Button variant="secondary" onClick={() => setAdding(true)}>
                Add information
              </Button>
            </div>
          )}
          {retired.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm font-semibold text-muted">Retired ({retired.length})</summary>
              <ul className="m-0 flex list-none flex-col p-0">
                {retired.map((entry) => (
                  <Entry key={entry.id} entry={entry} />
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </Panel>
  );
}
