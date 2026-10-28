// Add or edit a person who is analysed (a school's teacher; owner, 2026-10-28): their name and the units they work in
// (class-sections), owners and admins only. A record only: nobody is invited to sign in. The first unit ticked is the
// person's home unit.

import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { useOrganisation } from "../../api/hooks";
import type { Me, PersonItem } from "../../api/types";
import { unitLabel, unitTree, unitWords } from "../../app/units";
import { Button, Checkbox, Dialog, Input, useToast } from "../../design";

export function PersonDialog({ me, person, onClose }: { me: Me; person?: PersonItem; onClose: () => void }) {
  const labels = me.tenant.labels;
  const words = unitWords(labels);
  const tree = unitTree(me.tenant.units);
  const { createPerson, changePerson } = useOrganisation();
  const toast = useToast();
  const [name, setName] = useState(person?.name ?? "");
  const [chosen, setChosen] = useState<string[]>(person?.unit_ids ?? (person?.unit_id ? [person.unit_id] : []));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const who = labels.person.toLowerCase();

  const toggle = (id: string, on: boolean) =>
    setChosen((current) => (on ? [...current.filter((c) => c !== id), id] : current.filter((c) => c !== id)));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (person) await changePerson.mutateAsync({ id: person.id, name: name.trim(), unit_ids: chosen });
      else await createPerson.mutateAsync({ name: name.trim(), unit_ids: chosen });
      toast.show({
        tone: "success",
        title: person ? `${name.trim()} updated` : `${name.trim()} added`,
        duration: 4_000,
      });
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not save. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const box = (id: string, label: string) => (
    <Checkbox key={id} label={label} checked={chosen.includes(id)} onChange={(e) => toggle(id, e.target.checked)} />
  );

  return (
    <Dialog
      title={person ? `Edit ${person.name}` : `Add a ${who}`}
      description={`A record for uploading and reports; no sign-in is created.`}
      onClose={onClose}
    >
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="m-0 rounded bg-danger-tint px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
        <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
          <legend className="mb-1 text-sm font-semibold text-ink">
            {words.groups} and {words.subs.toLowerCase()} they teach
          </legend>
          {tree.length === 0 ? (
            <p className="m-0 text-sm text-muted">No {words.groups.toLowerCase()} yet: add them in Settings first.</p>
          ) : (
            <div className="flex max-h-[320px] flex-col gap-3 overflow-y-auto pr-1">
              {tree.map((group) =>
                group.children.length ? (
                  <div key={group.id} className="flex flex-col gap-1">
                    <span className="text-small font-semibold text-muted">{group.name}</span>
                    <div className="flex flex-wrap gap-x-5">{group.children.map((sub) => box(sub.id, sub.name))}</div>
                  </div>
                ) : (
                  box(group.id, group.name)
                ),
              )}
            </div>
          )}
          {chosen.length > 0 && (
            <p className="m-0 text-small text-muted">
              Home: {unitLabel(me.tenant.units, chosen[0])}. Each {labels.recording.toLowerCase()} is filed under the
              one chosen at upload.
            </p>
          )}
        </fieldset>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || !name.trim()}>
            {busy ? "Saving…" : person ? "Save" : `Add ${who}`}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
