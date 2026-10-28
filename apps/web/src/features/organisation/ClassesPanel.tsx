// Classes and sections (owner, 2026-10-28) on the Settings page, for owners and admins: add a top-level unit (a
// class), add units under it (sections), and rename either. The words come from the tenant's labels (app/units.ts).

import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { useOrganisation } from "../../api/hooks";
import type { Me } from "../../api/types";
import { unitTree, unitWords } from "../../app/units";
import { Button, Input, Panel, useToast } from "../../design";

function InlineForm({
  label,
  submitLabel,
  initial = "",
  onSubmit,
  onCancel,
}: {
  label: string;
  submitLabel: string;
  initial?: string;
  onSubmit: (name: string) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(initial);
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(undefined);
    try {
      await onSubmit(name.trim());
      setName("");
      onCancel?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not save. Please try again.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={(e) => void submit(e)} className="flex flex-wrap items-end gap-2">
      <Input
        label={label}
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={error}
        maxLength={120}
        className="min-w-[200px] flex-1"
      />
      <Button type="submit" variant="secondary" disabled={busy || !name.trim()}>
        {submitLabel}
      </Button>
      {onCancel && (
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      )}
    </form>
  );
}

export function ClassesPanel({ me }: { me: Me }) {
  const words = unitWords(me.tenant.labels);
  const tree = unitTree(me.tenant.units);
  const { createUnit, renameUnit } = useOrganisation();
  const toast = useToast();
  const [renaming, setRenaming] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const lower = (s: string) => s.toLowerCase();

  const rename = (id: string, current: string) => (
    <InlineForm
      label={`New name for ${current}`}
      submitLabel="Rename"
      initial={current}
      onSubmit={async (name) => {
        await renameUnit.mutateAsync({ id, name });
        toast.show({ tone: "success", title: `Renamed to ${name}`, duration: 4_000 });
      }}
      onCancel={() => setRenaming(null)}
    />
  );

  return (
    <Panel
      title={`${words.groups} and ${lower(words.subs)}`}
      description={`Each ${lower(me.tenant.labels.person)} works in one or more of these; ${lower(me.tenant.labels.recording_plural)} are filed under them.`}
    >
      {tree.length === 0 && (
        <p className="m-0 text-sm text-muted">No {lower(words.groups)} yet. Add the first one below.</p>
      )}
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {tree.map((group) => (
          <li key={group.id} className="flex flex-col gap-2.5 rounded-card border border-line-subtle px-4 py-3">
            {renaming === group.id ? (
              rename(group.id, group.name)
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-ink">{group.name}</span>
                <span className="flex gap-1">
                  <Button variant="ghost" onClick={() => setRenaming(group.id)}>
                    Rename
                  </Button>
                  <Button variant="ghost" onClick={() => setAdding(group.id)}>
                    Add {lower(words.sub)}
                  </Button>
                </span>
              </div>
            )}
            {group.children.length > 0 && (
              <ul aria-label={`${words.subs} of ${group.name}`} className="m-0 flex list-none flex-wrap gap-2 p-0">
                {group.children.map((sub) =>
                  renaming === sub.id ? (
                    <li key={sub.id} className="w-full">
                      {rename(sub.id, sub.name)}
                    </li>
                  ) : (
                    <li key={sub.id}>
                      <button
                        type="button"
                        onClick={() => setRenaming(sub.id)}
                        title={`Rename ${group.name} · ${sub.name}`}
                        className="min-h-touch rounded-full border border-line bg-surface-subtle px-3.5 text-sm text-ink hover:border-primary-border"
                      >
                        {sub.name}
                      </button>
                    </li>
                  ),
                )}
              </ul>
            )}
            {adding === group.id && (
              <InlineForm
                label={`New ${lower(words.sub)} in ${group.name}`}
                submitLabel={`Add ${lower(words.sub)}`}
                onSubmit={async (name) => {
                  await createUnit.mutateAsync({ name, parent_id: group.id });
                  toast.show({ tone: "success", title: `${group.name} · ${name} added`, duration: 4_000 });
                }}
                onCancel={() => setAdding(null)}
              />
            )}
          </li>
        ))}
      </ul>
      <InlineForm
        label={`New ${lower(words.group)}`}
        submitLabel={`Add ${lower(words.group)}`}
        onSubmit={async (name) => {
          await createUnit.mutateAsync({ name, parent_id: null });
          toast.show({ tone: "success", title: `${name} added`, duration: 4_000 });
        }}
      />
    </Panel>
  );
}
