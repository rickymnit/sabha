// Period picker for the overview (P6.4b): presets or a custom pair of days, in India Standard Time.

import { useState } from "react";

import { Input, Select } from "../../design";
import { presetRange, rangeProblem, type DayRange, type RangePreset } from "./range";

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "month", label: "This month" },
  { value: "custom", label: "Custom range" },
];

export interface DateRangePickerProps {
  preset: RangePreset;
  range: DayRange;
  onChange: (preset: RangePreset, range: DayRange) => void;
  /** Injected for tests; defaults to the current time. */
  now?: () => Date;
}

export function DateRangePicker({ preset, range, onChange, now = () => new Date() }: DateRangePickerProps) {
  const [draft, setDraft] = useState<DayRange>(range);
  const [problem, setProblem] = useState<string | null>(null);

  function choosePreset(next: RangePreset) {
    if (next === "custom") {
      setDraft(range);
      onChange("custom", range);
      return;
    }
    setProblem(null);
    onChange(next, presetRange(next, now()));
  }

  function editDay(part: keyof DayRange, value: string) {
    const next = { ...draft, [part]: value };
    setDraft(next);
    const reason = rangeProblem(next, now());
    setProblem(reason);
    if (!reason) onChange("custom", next);
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <Select label="Period" value={preset} onChange={(e) => choosePreset(e.target.value as RangePreset)}>
        {PRESETS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </Select>
      {preset === "custom" && (
        <>
          <Input
            type="date"
            label="From"
            value={draft.start}
            max={draft.end}
            onChange={(e) => editDay("start", e.target.value)}
            error={problem ?? undefined}
          />
          <Input
            type="date"
            label="To"
            value={draft.end}
            min={draft.start}
            onChange={(e) => editDay("end", e.target.value)}
          />
        </>
      )}
    </div>
  );
}
