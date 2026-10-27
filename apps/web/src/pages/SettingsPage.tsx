// /settings (P1.7; docs/design/04-workspace-setup.png): owners and admins rename the organisation and the words used
// across the product, and switch conversation types on or off. Saving updates the menu and every page at once
// (useUpdateSettings refetches /v1/me). Types without a rubric for the organisation cannot be switched on, and the
// plan caps how many are on (the API enforces both; the page explains them before anyone tries).

import { useId, useState, type FormEvent } from "react";
import { useOutletContext } from "react-router-dom";

import { ApiError } from "../api/client";
import { useSettings, useUpdateSettings } from "../api/hooks";
import type { Me, SettingsChange, TenantSettings } from "../api/types";
import {
  Button,
  Checkbox,
  EmptyState,
  Icon,
  Input,
  PageHeader,
  Panel,
  Skeleton,
  SkeletonGroup,
  TypeDot,
  useToast,
  type ConversationType,
} from "../design";
import type { Labels } from "../features/report/types";
import { TYPE_INFO } from "../app/conversationTypes";
import { capitalise } from "../app/format";

const EDITORS = ["owner", "admin"];

/** What each word means, for the person renaming it (Setup.dc.html:144-147). */
const WORDS: { key: keyof Labels; label: string; hint: string }[] = [
  { key: "person", label: "Person analysed", hint: "One of the staff whose conversations are analysed" },
  { key: "person_plural", label: "Several of them", hint: "The menu item and lists" },
  { key: "recording", label: "A recording", hint: "One analysed conversation" },
  { key: "recording_plural", label: "Several recordings", hint: "The menu item and lists" },
  { key: "unit", label: "Group", hint: "Where people belong: a class, branch or team" },
  { key: "manager", label: "Manager", hint: "Who coaches them" },
];
const MAX_WORD = 40;
const MAX_NAME = 120;

interface Draft {
  name: string;
  labels: Labels;
  types: ConversationType[];
}

function draftOf(settings: TenantSettings): Draft {
  return { name: settings.name, labels: { ...settings.labels }, types: [...settings.enabled_types] };
}

/** Only what changed, trimmed; empty when nothing did. */
function changeOf(saved: Draft, draft: Draft, order: ConversationType[]): SettingsChange {
  const change: SettingsChange = {};
  if (draft.name.trim() !== saved.name) change.name = draft.name.trim();
  const words = Object.fromEntries(
    WORDS.map(({ key }) => [key, draft.labels[key].trim()] as const).filter(([key, v]) => v !== saved.labels[key]),
  );
  if (Object.keys(words).length) change.labels = words;
  const types = order.filter((t) => draft.types.includes(t));
  if (types.join() !== saved.types.join()) change.enabled_types = types;
  return change;
}

function wordError(value: string, limit: number): string | undefined {
  if (!value.trim()) return "This cannot be empty.";
  if (value.trim().length > limit) return `Use at most ${limit} characters.`;
  return undefined;
}

export function SettingsPage() {
  const me = useOutletContext<Me>();
  const settings = useSettings();
  if (!EDITORS.includes(me.user.role)) {
    return (
      <Panel>
        <EmptyState
          className="py-14"
          headingAs="h1"
          icon={<Icon name="settings" size={26} />}
          title="Only owners and administrators can change settings"
          description="Ask your administrator if something here needs changing."
        />
      </Panel>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Your organisation's name, the words used across the product and the conversations you analyse."
      />
      {settings.isError ? (
        <Panel>
          <EmptyState
            icon={<Icon name="alert" size={26} />}
            title="We couldn't load your settings"
            description="Please try again in a moment."
            action={<Button onClick={() => void settings.refetch()}>Try again</Button>}
          />
        </Panel>
      ) : settings.isPending ? (
        <Panel>
          <SkeletonGroup label="Loading settings" className="flex flex-col gap-4">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-11 w-full max-w-md" />
            <Skeleton className="h-11 w-full max-w-md" />
          </SkeletonGroup>
        </Panel>
      ) : (
        <SettingsForm settings={settings.data} />
      )}
    </div>
  );
}

function SettingsForm({ settings }: { settings: TenantSettings }) {
  const toast = useToast();
  const save = useUpdateSettings();
  const typesHeading = useId();
  const order = settings.types.map((t) => t.type);
  const available = new Set(settings.types.filter((t) => t.available).map((t) => t.type));
  const [saved, setSaved] = useState(() => draftOf(settings));
  const [draft, setDraft] = useState(() => draftOf(settings));
  const [typesError, setTypesError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const change = changeOf(saved, draft, order);
  const dirty = Object.keys(change).length > 0;
  const nameError = submitted ? wordError(draft.name, MAX_NAME) : undefined;
  const errors = Object.fromEntries(
    WORDS.map(({ key }) => [key, submitted ? wordError(draft.labels[key], MAX_WORD) : undefined]),
  );
  const overLimit = draft.types.length > settings.max_types;
  const noTypes = draft.types.length === 0;

  function toggle(type: ConversationType, on: boolean) {
    setTypesError(null);
    setDraft((d) => ({ ...d, types: on ? [...d.types, type] : d.types.filter((t) => t !== type) }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    const invalid = wordError(draft.name, MAX_NAME) || WORDS.some(({ key }) => wordError(draft.labels[key], MAX_WORD));
    if (invalid || overLimit || noTypes || !dirty) return;
    try {
      const result = await save.mutateAsync(change);
      setSaved(draftOf(result));
      setDraft(draftOf(result));
      setSubmitted(false);
      toast.show({
        tone: "success",
        title: "Settings saved",
        message: "Everyone sees the new words now.",
        duration: 4000,
      });
    } catch (error) {
      if (error instanceof ApiError && (error.code === "plan_limit" || error.code === "type_unavailable")) {
        setTypesError(error.message);
        return;
      }
      toast.show({
        tone: "error",
        title: "Your changes were not saved",
        message: "Please try again in a moment.",
        requestId: error instanceof ApiError ? error.requestId : undefined,
      });
    }
  }

  const discard = () => {
    setDraft(saved);
    setSubmitted(false);
    setTypesError(null);
  };

  return (
    <form onSubmit={submit} noValidate className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex min-w-0 flex-col gap-6">
        <Panel title="Organisation">
          <Input
            label="Organisation name"
            value={draft.name}
            maxLength={MAX_NAME + 20}
            error={nameError}
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            className="max-w-md"
          />
        </Panel>

        <Panel
          title="Words used across the product"
          description="Sabha uses these words in every menu, list and report, for everyone in your organisation."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {WORDS.map(({ key, label, hint }) => (
              <Input
                key={key}
                label={label}
                hint={hint}
                value={draft.labels[key]}
                maxLength={MAX_WORD + 10}
                error={errors[key]}
                onChange={(e) => setDraft((d) => ({ ...d, labels: { ...d.labels, [key]: e.target.value } }))}
              />
            ))}
          </div>
        </Panel>

        <Panel
          title="Conversation types"
          description={`Your plan covers ${settings.max_types === order.length ? `all ${order.length}` : `any ${settings.max_types}`} at a time. Switching one off stops new uploads of it; finished reports stay available.`}
        >
          <fieldset aria-labelledby={typesHeading} className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend id={typesHeading} className="sr-only">
              Conversation types
            </legend>
            {order.map((type) => {
              const on = draft.types.includes(type);
              const ready = available.has(type);
              return (
                <Checkbox
                  key={type}
                  checked={on}
                  disabled={!ready && !on}
                  onChange={(e) => toggle(type, e.target.checked)}
                  className="rounded border border-line px-3.5"
                  label={TYPE_INFO[type].name}
                  description={
                    ready
                      ? TYPE_INFO[type].description
                      : "Not set up for your organisation yet. Ask your Sabha contact."
                  }
                />
              );
            })}
          </fieldset>
          <p className="mb-0 mt-3 text-small text-muted" aria-live="polite">
            {draft.types.length} of {order.length} conversation types on.
          </p>
          {(typesError || (submitted && (overLimit || noTypes))) && (
            <p role="alert" className="mb-0 mt-1 text-small font-semibold text-danger">
              {typesError ??
                (noTypes
                  ? "Keep at least one conversation type on."
                  : `Your plan covers ${settings.max_types} conversation types at a time. Switch one off first.`)}
            </p>
          )}
        </Panel>
      </div>

      <aside aria-label="Preview" className="flex flex-col gap-6">
        <Preview draft={draft} />
      </aside>

      <div className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center justify-end gap-3 border-t border-line bg-surface px-4 py-3 md:mx-0 md:rounded-panel md:border lg:col-span-2">
        <span className="mr-auto text-small text-muted" aria-live="polite">
          {dirty ? "You have unsaved changes." : "All changes saved."}
        </span>
        <Button type="button" variant="secondary" onClick={discard} disabled={!dirty || save.isPending}>
          Discard
        </Button>
        <Button type="submit" disabled={!dirty || save.isPending}>
          {save.isPending ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}

/** "How your team will see it" (Setup.dc.html): the menu in the words being typed. */
function Preview({ draft }: { draft: Draft }) {
  const word = (key: keyof Labels) => capitalise(draft.labels[key].trim() || "…");
  return (
    <Panel title="How your team will see it" headingAs="h2">
      <div aria-hidden="true" className="flex flex-col gap-1 text-sm">
        <p className="m-0 truncate font-semibold text-ink">{draft.name.trim() || "…"}</p>
        {["Overview", word("recording_plural"), "Reviews", word("person_plural"), "Upload"].map((item, i) => (
          <span
            key={item + i}
            className={
              i === 0 ? "rounded bg-primary-tint px-2 py-1.5 font-semibold text-primary-hover" : "px-2 py-1.5 text-ink"
            }
          >
            {item}
          </span>
        ))}
        {draft.types.length > 1 && (
          <>
            <span className="px-2 pb-1 pt-3 text-caption font-semibold text-muted-2">Conversation types</span>
            {draft.types.map((t) => (
              <TypeDot key={t} type={t} label={TYPE_INFO[t].name} className="px-2 py-1" />
            ))}
          </>
        )}
      </div>
      <dl className="m-0 mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 border-t border-line-subtle pt-4 text-sm">
        {WORDS.map(({ key, label }) => (
          <div key={key} className="contents">
            <dt className="text-muted">{label}</dt>
            <dd className="m-0 truncate font-semibold text-ink">{draft.labels[key].trim() || "…"}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}
