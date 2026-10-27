import type { ReactNode } from "react";

import { cx } from "./cx";
import { speakerSpans, staffShare, type SpeakerKind, type SpeakerSegment } from "./speakerSpans";

// Who spoke when, UI v2 (docs/design/v2/): "row" is the thin bar in list rows (01-overview, 02-recordings), "card" the
// talk-and-listen split (04-sales-report), "lanes" one lane per side on the report timeline (03-lesson-report). Staff
// is blue, everyone else amber; uncovered track is silence or no data.

const fills: Record<SpeakerKind, string> = { staff: "bg-speaker-staff", other: "bg-speaker-other" };

const percent = (share: number) => `${Math.round(share * 100)}%`;

interface BaseProps {
  /** Speaker turns on the original recording timeline. */
  segments: readonly SpeakerSegment[];
  durationMs: number;
  className?: string;
}

export interface SpeakerStripRowProps extends BaseProps {
  size: "row";
  /** Accessible name, for example "Teacher 84% of speech, students 16%". */
  label: string;
}

export interface SpeakerStripCardProps extends Omit<BaseProps, "durationMs"> {
  size: "card";
  /** Names under the bar, for example the rep's first name and "Client". */
  staffLabel: string;
  otherLabel: string;
}

export interface SpeakerStripLanesProps extends BaseProps {
  size: "lanes";
  staffLabel: string;
  otherLabel: string;
  /** Drawn over both lanes, positioned in percent of the recording: evidence pins, the playhead. */
  overlay?: ReactNode;
}

export type SpeakerStripProps = SpeakerStripRowProps | SpeakerStripCardProps | SpeakerStripLanesProps;

function Spans({
  segments,
  durationMs,
  mergeGapPct,
}: {
  segments: readonly SpeakerSegment[];
  durationMs: number;
  mergeGapPct: number;
}) {
  return (
    <>
      {speakerSpans(segments, durationMs, mergeGapPct).map((span) => (
        <span
          key={`${span.speaker}-${span.left}`}
          data-speaker={span.speaker}
          className={cx("absolute inset-y-0", fills[span.speaker])}
          style={{ left: `${span.left}%`, width: `${span.width}%` }}
        />
      ))}
    </>
  );
}

export function SpeakerStrip(props: SpeakerStripProps) {
  if (props.size === "row") {
    const { segments, durationMs, label, className } = props;
    return (
      <span
        role="img"
        aria-label={label}
        className={cx("relative block h-1.5 w-full overflow-hidden rounded-full bg-track", className)}
      >
        <Spans segments={segments} durationMs={durationMs} mergeGapPct={0.6} />
      </span>
    );
  }

  if (props.size === "card") {
    const { segments, staffLabel, otherLabel, className } = props;
    const share = staffShare(segments);
    return (
      <div className={className}>
        <div className="flex h-2.5 overflow-hidden rounded-full bg-track" aria-hidden="true">
          {share !== null && (
            <>
              <span className="bg-speaker-staff" style={{ width: percent(share) }} />
              <span className="flex-1 bg-speaker-other" />
            </>
          )}
        </div>
        {share !== null && (
          <div className="mt-2 flex justify-between text-sm font-semibold">
            <span className="text-primary">
              {staffLabel} {percent(share)}
            </span>
            <span className="text-warning">
              {otherLabel} {100 - Math.round(share * 100)}%
            </span>
          </div>
        )}
      </div>
    );
  }

  const { segments, durationMs, staffLabel, otherLabel, overlay, className } = props;
  // Every cell is placed explicitly, so the overlay can cover both tracks without pushing them to new rows.
  const lanes: { kind: SpeakerKind; label: string; tone: string; row: string }[] = [
    { kind: "staff", label: staffLabel, tone: "text-primary", row: "row-start-1" },
    { kind: "other", label: otherLabel, tone: "text-warning", row: "row-start-2" },
  ];
  return (
    <div className={cx("grid grid-cols-[72px_1fr] items-center gap-x-3 gap-y-1.5", className)}>
      {lanes.map((lane) => (
        <div key={lane.kind} className="contents">
          <span className={cx("col-start-1 truncate text-caption font-semibold", lane.row, lane.tone)}>
            {lane.label}
          </span>
          <span className={cx("relative col-start-2 block h-5 overflow-hidden rounded-sm bg-surface-subtle", lane.row)}>
            <Spans segments={segments.filter((s) => s.speaker === lane.kind)} durationMs={durationMs} mergeGapPct={0} />
          </span>
        </div>
      ))}
      {overlay && <div className="relative col-start-2 row-span-2 row-start-1 h-full">{overlay}</div>}
    </div>
  );
}
