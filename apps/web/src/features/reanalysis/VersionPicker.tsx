// Which analysis of a re-analysed recording to show (P2.8): the latest by default, or an earlier version as history.

import { useId } from "react";

import type { AnalysisVersion } from "../../api/types";
import { versionLabel } from "./versionLabel";

export interface VersionPickerProps {
  versions: readonly AnalysisVersion[];
  /** The analysis shown; undefined for the latest. */
  selected: string | undefined;
  onSelect: (analysisId: string | undefined) => void;
}

export function VersionPicker({ versions, selected, onSelect }: VersionPickerProps) {
  const id = useId();
  const latest = versions[0];
  if (!latest || versions.length < 2) return null;
  return (
    <span className="flex flex-wrap items-center gap-2 text-sm">
      <label htmlFor={id} className="font-semibold text-ink-2">
        Analysis
      </label>
      <select
        id={id}
        value={selected ?? latest.id}
        onChange={(e) => onSelect(e.target.value === latest.id ? undefined : e.target.value)}
        className="min-h-touch rounded border border-line-input bg-surface px-3"
      >
        {versions.map((v) => (
          <option key={v.id} value={v.id}>
            {versionLabel(v, v.id === latest.id)}
          </option>
        ))}
      </select>
    </span>
  );
}
