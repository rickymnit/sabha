// Overview (P6.4b): headline numbers and "Where coaching helps most" for a period, matching
// docs/design/01-overview.png. "Processing now" and the recent recordings table arrive with P6.4a (live API).
// Numbers come from GET /v1/overview; any number whose underlying n is 0 is hidden, never shown as 0.

import { EmptyState, MetricStrip, PageHeader, Panel, ScoreBar, Skeleton, scoreBand, type Metric } from "../../design";
import type { Labels } from "../report/types";
import { DateRangePicker } from "./DateRangePicker";
import { coachingItems, overviewMetrics, type TypeNames } from "./metrics";
import { describeRange, type DayRange, type RangePreset } from "./range";
import type { OverviewStats } from "./types";

export interface OverviewPageProps {
  /** Undefined while loading. */
  stats: OverviewStats | undefined;
  /** "All campuses", or the chosen unit, from the tenant's labels. */
  scopeLabel: string;
  preset: RangePreset;
  range: DayRange;
  onRangeChange: (preset: RangePreset, range: DayRange) => void;
  typeNames: TypeNames;
  labels: Labels;
  rubricHref: (rubricId: string) => string;
  now?: () => Date;
}

const scoreTone = { low: "text-danger", mid: "text-warning", good: "text-success" } as const;

export function OverviewPage(props: OverviewPageProps) {
  const { stats, scopeLabel, preset, range, onRangeChange, typeNames, labels, now } = props;
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Overview"
        description={`${scopeLabel}, ${describeRange(range)}`}
        actions={<DateRangePicker preset={preset} range={range} onChange={onRangeChange} now={now} />}
      />
      {stats === undefined ? (
        <Skeleton className="h-[126px] rounded-panel" />
      ) : (
        <Headline stats={stats} typeNames={typeNames} labels={labels} />
      )}
      {stats !== undefined && <Coaching {...props} stats={stats} />}
    </div>
  );
}

function Headline({ stats, typeNames, labels }: { stats: OverviewStats; typeNames: TypeNames; labels: Labels }) {
  const specs = overviewMetrics(stats, typeNames, labels);
  if (specs.length === 0) {
    return (
      <Panel title="In this period">
        <EmptyState
          headingAs="h3"
          title={`No ${labels.recording_plural} analysed in this period`}
          description="Numbers appear here once recordings from these dates have been analysed."
        />
      </Panel>
    );
  }
  const metrics: Metric[] = specs.map(({ footText, footHref, ...m }) => ({
    ...m,
    foot: footHref ? <a href={footHref}>{footText}</a> : footText,
    footTone: footHref ? undefined : "muted",
  }));
  return <MetricStrip label="In this period" metrics={metrics} />;
}

function Coaching({ stats, typeNames, labels, rubricHref }: OverviewPageProps & { stats: OverviewStats }) {
  const items = coachingItems(stats.coaching);
  return (
    <Panel
      title="Where coaching helps most"
      description="Lowest median dimension scores in this period"
      className="max-w-[420px]"
    >
      {items.length === 0 ? (
        <p className="m-0 text-sm text-muted">Not enough verified scores in this period yet.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {items.map((item) => (
            <li key={`${item.rubric_id}:${item.dimension_key}`} className="flex flex-col gap-1.5">
              <div className="flex justify-between gap-2 text-table font-semibold">
                <a href={rubricHref(item.rubric_id)} className="text-ink no-underline hover:underline">
                  {item.dimension_name}
                </a>
                <span className={scoreTone[scoreBand(item.median)]}>{item.median.toFixed(1)}</span>
              </div>
              <ScoreBar score={item.median} hideValue valueText={`Median ${item.median.toFixed(1)} of 5`} />
              <span className="text-small text-muted">
                {typeNames[item.type]}, {item.n} {item.n === 1 ? labels.recording : labels.recording_plural}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
