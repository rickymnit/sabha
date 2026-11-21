// "Words Sabha should know" (ADR 0019): the organisation's own words, and how speech-to-text gets them wrong. Saved
// whole with PATCH /v1/settings; used for conversations analysed from then on.

import { useState } from "react";

import { ApiError } from "../../api/client";
import { useUpdateSettings } from "../../api/hooks";
import type { VocabularyTerm } from "../../api/types";
import { Button, Icon, Input, Panel, useToast } from "../../design";

interface Row {
  key: number;
  term: string;
  spellings: string; // comma separated while editing
}

let nextKey = 1;
const rowsOf = (terms: VocabularyTerm[]): Row[] =>
  terms.map((t) => ({ key: nextKey++, term: t.term, spellings: t.sounds_like.join(", ") }));

const termsOf = (rows: Row[]): VocabularyTerm[] =>
  rows
    .map((r) => ({
      term: r.term.trim(),
      sounds_like: r.spellings
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    }))
    .filter((t) => t.term);

export function VocabularyPanel({ vocabulary }: { vocabulary: VocabularyTerm[] }) {
  const save = useUpdateSettings();
  const toast = useToast();
  const [rows, setRows] = useState<Row[]>(() => rowsOf(vocabulary));
  const saved = JSON.stringify(vocabulary); // the page remounts this panel (key) when the saved list changes
  const dirty = JSON.stringify(termsOf(rows)) !== saved;

  const set = (key: number, change: Partial<Row>) =>
    setRows((current) => current.map((r) => (r.key === key ? { ...r, ...change } : r)));

  async function submit() {
    try {
      await save.mutateAsync({ vocabulary: termsOf(rows) });
      toast.show({
        tone: "success",
        title: "Words saved",
        message: "Conversations analysed from now on use them.",
        duration: 4000,
      });
    } catch (error) {
      toast.show({
        tone: "error",
        title: "Your words were not saved",
        message: "Please try again in a moment.",
        requestId: error instanceof ApiError ? error.requestId : undefined,
      });
    }
  }

  return (
    <Panel
      title="Words Sabha should know"
      description="Your company's words, and how they are misheard. Sabha listens for them and fixes them in every transcript."
      actions={
        <Button onClick={() => void submit()} disabled={!dirty || save.isPending}>
          {save.isPending ? "Saving…" : "Save words"}
        </Button>
      }
    >
      <ul className="flex flex-col gap-3">
        <li className="hidden grid-cols-[minmax(0,1fr)_minmax(0,2fr)_40px] gap-3 text-[13px] text-muted sm:grid">
          <span>Correct word</span>
          <span>Heard as (separate with commas)</span>
          <span />
        </li>
        {rows.map((row) => (
          <li key={row.key} className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_40px] sm:gap-3">
            <Input
              label="Correct word"
              hideLabel
              value={row.term}
              maxLength={60}
              placeholder="Schoollog"
              onChange={(e) => set(row.key, { term: e.target.value })}
            />
            <Input
              label={`How ${row.term || "this word"} is misheard`}
              hideLabel
              value={row.spellings}
              placeholder="schoolo, school log"
              onChange={(e) => set(row.key, { spellings: e.target.value })}
            />
            <Button
              variant="ghost"
              aria-label={`Remove ${row.term || "this word"}`}
              onClick={() => setRows((current) => current.filter((r) => r.key !== row.key))}
            >
              <Icon name="close" size={16} />
            </Button>
          </li>
        ))}
      </ul>
      <div className="mt-4">
        <Button
          variant="secondary"
          onClick={() => setRows((current) => [...current, { key: nextKey++, term: "", spellings: "" }])}
        >
          Add a word
        </Button>
      </div>
    </Panel>
  );
}
