// Overview (UI v2, docs/design/v2/01-overview.png): a greeting, the unit switcher and period, four tiles with their
// trend bars, "Needs your decision" beside "Processing now", "Where coaching will help most" as a table by unit with
// an eight-week trend, and the recent recordings. The page around it (pages/OverviewRoute.tsx) passes the decision
// list, the processing panel and the recent table in. Numbers come from GET /v1/overview; any number whose n is 0
// is hidden, never shown as 0.

import type { ReactNode } from "react";

import {
  BarSpark,
  EmptyState,
  Panel,
  SegmentedControl,
  Skeleton,
  cx,
  scoreBand,
  type ConversationType,
} from "../../design";
import type { Labels } from "../report/types";
import { DateRangePicker } from "./DateRangePicker";
import { ALL_UNITS, coachingRows, mainType, overviewTiles, type Tile, type TypeNames } from "./metrics";
import { describeRange, type DayRange, type RangePreset } from "./range";
import type { CoachingItem, OverviewStats } from "./types";

export interface OverviewPageProps {
  /** Undefined while loading. */
  stats: OverviewStats | undefined;
  /** First name for the greeting. */
  name: string;
  preset: RangePreset;
  range: DayRange;
  onRangeChange: (preset: RangePreset, range: DayRange) => void;
  /** What the previous period is called in "Up 32 on last week". */
  compare: string;
  /** The chosen top-level unit, or ALL_UNITS (metrics.ts). */
  unit: string;
  onUnitChange: (unit: string) => void;
  typeNames: TypeNames;
  labels: Labels;
  enabledTypes: readonly ConversationType[];
  /** How many things wait for a decision, for the greeting line. */
  waiting?: number;
  now?: () => Date;
  /** "Needs your decision" panel. */
  decisions?: ReactNode;
  /** "Processing now" panel. */
  processing?: ReactNode;
  /** Recent recordings. */
  recent?: ReactNode;
}

function greeting(now: Date): string {
  const hour = Number(new Intl.DateTimeFormat("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" })
    .format(now)); // prettier-ignore
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export function OverviewPage(props: OverviewPageProps) {
  const { stats, name, preset, range, onRangeChange, unit, onUnitChange, labels, waiting, now } = props;
  const today = (now ?? (() => new Date()))();
  const units = stats?.units ?? [];
  const things = labels.recording_plural.toLowerCase();
  const summary = stats
    ? `${stats.recordings_analysed} ${stats.recordings_analysed === 1 ? labels.recording.toLowerCase() : things} analysed, ${describeRange(range)}.`
    : describeRange(range);
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="m-0 text-title font-bold text-ink">
            {greeting(today)}, {name}
          </h1>
          <p className="m-0 text-sm text-muted">
            {summary}
            {waiting ? ` ${waiting} ${waiting === 1 ? "needs" : "need"} a decision from you.` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {units.length > 1 && (
            <SegmentedControl
              label="Show"
              value={unit}
              onChange={onUnitChange}
              options={[{ value: ALL_UNITS, label: "All" }, ...units.map((u) => ({ value: u.id, label: u.name }))]}
            />
          )}
          <DateRangePicker preset={preset} range={range} onChange={onRangeChange} now={now} />
        </div>
      </header>
      {stats === undefined ? <Skeleton className="h-[118px] rounded-panel" /> : <Tiles {...props} stats={stats} />}
      {(props.decisions || props.processing) && (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
          {props.decisions}
          {props.processing}
        </div>
      )}
      {stats !== undefined && <Coaching {...props} stats={stats} />}
      {props.recent}
    </div>
  );
}

const footTones: Record<Tile["footTone"], string> = {
  good: "text-success",
  bad: "text-danger",
  muted: "text-muted",
};

function Tiles({ stats, typeNames, labels, compare, enabledTypes }: OverviewPageProps & { stats: OverviewStats }) {
  const tiles = overviewTiles(stats, typeNames, labels, compare, enabledTypes);
  if (tiles.length === 0) {
    return (
      <Panel title="In this period">
        <EmptyState
          headingAs="h3"
          title={`No ${labels.recording_plural.toLowerCase()} analysed in this period`}
          description="Numbers appear here once recordings from these dates have been analysed."
        />
      </Panel>
    );
  }
  return (
    <section
      aria-label="In this period"
      className="grid overflow-hidden rounded-panel border border-line bg-surface sm:grid-cols-2 xl:grid-cols-4"
    >
      {tiles.map((tile, i) => (
        <div
          key={tile.id}
          className={cx(
            "flex items-end justify-between gap-3 border-line-subtle px-5 py-4",
            i > 0 && "border-t sm:border-t-0",
            i % 2 === 1 && "sm:border-l",
            i >= 2 && "sm:border-t xl:border-t-0",
            i > 0 && "xl:border-l",
          )}
        >
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-sm text-muted">{tile.label}</span>
            <span className="text-metric font-bold tabular-nums text-ink">
              {tile.value}
              {tile.suffix && <span className="text-md font-medium text-muted">{tile.suffix}</span>}
            </span>
            {tile.foot && <span className={cx("text-small", footTones[tile.footTone])}>{tile.foot}</span>}
          </div>
          <BarSpark
            values={tile.bars}
            label={tile.barsLabel}
            tone={tile.id === "resolved" && tile.footTone === "bad" ? "warning" : "primary"}
            className="shrink-0"
          />
        </div>
      ))}
    </section>
  );
}

const cellTones = {
  low: "bg-danger-tint text-danger",
  mid: "bg-warning-tint text-warning",
  good: "bg-success-tint text-success",
} as const;

function Cell({ value }: { value: { median: number; n: number } | undefined }) {
  if (!value || value.n === 0) {
    return (
      <span className="block rounded-md bg-surface-subtle py-2 text-center text-muted-2">
        <span aria-hidden="true">—</span>
        <span className="sr-only">No verified scores</span>
      </span>
    );
  }
  return (
    <span
      className={cx("block rounded-md py-2 text-center font-semibold tabular-nums", cellTones[scoreBand(value.median)])}
    >
      {value.median.toFixed(1)}
    </span>
  );
}

function Coaching({ stats, typeNames, labels }: OverviewPageProps & { stats: OverviewStats }) {
  const rows = coachingRows(stats);
  const main = mainType(stats);
  const byUnit = !stats.unit_id && (stats.units?.length ?? 0) > 1 ? (stats.units ?? []) : [];
  const legend = (
    <ul className="m-0 flex list-none flex-wrap gap-3 p-0 text-small text-muted" aria-label="Colours">
      {[
        ["bg-danger-tint", "Below 3.0"],
        ["bg-warning-tint", "3.0 to 3.7"],
        ["bg-success-tint", "3.8 and above"],
      ].map(([swatch, text]) => (
        <li key={text} className="flex items-center gap-1.5">
          <span aria-hidden="true" className={cx("size-3 rounded-sm", swatch)} />
          {text}
        </li>
      ))}
    </ul>
  );
  return (
    <Panel
      flush
      title="Where coaching will help most"
      description={`Median ${main ? typeNames[main].toLowerCase() : ""} score${byUnit.length ? " by unit" : ""}, 1 to 5, verified evidence only`}
      actions={rows.length > 0 && legend}
    >
      {rows.length === 0 ? (
        <p className="m-0 px-5 py-4 text-sm text-muted">Not enough verified scores in this period yet.</p>
      ) : (
        <div className="overflow-x-auto px-5 py-3">
          <table className="w-full min-w-[560px] border-separate border-spacing-x-1.5 border-spacing-y-1 text-table">
            <thead>
              <tr className="text-left text-small font-medium text-muted">
                <th scope="col" className="py-1.5 font-medium">
                  Rubric point
                </th>
                {byUnit.length ? (
                  byUnit.map((u) => (
                    <th key={u.id} scope="col" className="py-1.5 text-center font-medium">
                      {u.name}
                    </th>
                  ))
                ) : (
                  <th scope="col" className="w-28 py-1.5 text-center font-medium">
                    Median
                  </th>
                )}
                <th scope="col" className="w-36 py-1.5 font-medium">
                  Trend, 8 weeks
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <CoachingRow
                  key={`${item.rubric_id}:${item.dimension_key}`}
                  item={item}
                  units={byUnit}
                  labels={labels}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function CoachingRow({ item, units, labels }: { item: CoachingItem; units: { id: string }[]; labels: Labels }) {
  const weekly = item.weekly ?? [];
  const values = weekly.map((w) => (w.median === null ? null : w.median / 5));
  const said = weekly.map((w) => (w.median === null ? "none" : w.median.toFixed(1))).join(", ");
  return (
    <tr>
      <th scope="row" className="py-1 text-left font-normal text-ink">
        {item.dimension_name}
        <span className="sr-only">
          , {item.n} {(item.n === 1 ? labels.recording : labels.recording_plural).toLowerCase()}
        </span>
      </th>
      {units.length ? (
        units.map((u) => (
          <td key={u.id} className="py-1">
            <Cell value={item.by_unit?.find((v) => v.unit_id === u.id)} />
          </td>
        ))
      ) : (
        <td className="py-1">
          <Cell value={item} />
        </td>
      )}
      <td className="py-1">
        {weekly.length > 0 && (
          <BarSpark values={values} label={`Weekly median: ${said}`} height={22} highlightLast={false} />
        )}
      </td>
    </tr>
  );
}
