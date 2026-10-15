// Recording timeline (Analysis.dc.html:120-171): legend, phases, speech bars coloured by role with removed silence
// in grey, numbered evidence pins for the selected dimension, and the playhead. Times are on the original timeline.

import { useMemo, type MouseEvent, type ReactNode } from "react";

import { cx } from "../../design";
import { formatClock, type RoleLabels, type Utterance } from "../transcript";
import { formatMinutes, formatPercent } from "./format";
import { buildBars, percentAt, talkShares, ticks, totalMs } from "./timeline";
import type { EvidenceQuote, Phase, TimeRange } from "./types";

/** The design draws 180 bars (Analysis.dc.html:349). */
const BAR_COUNT = 180;

export interface ReportTimelineProps {
  heading: ReactNode;
  utterances: readonly Utterance[];
  roles: RoleLabels;
  durationMs: number;
  removedSilence: readonly TimeRange[];
  phases?: readonly Phase[] | null;
  /** Evidence of the selected dimension, numbered from 1 in this order. */
  evidence: readonly EvidenceQuote[];
  /** Name of the selected dimension, for the caption. */
  dimensionName?: string;
  /** Playback position in ms, or null before anything has played. */
  currentMs: number | null;
  onSeek: (ms: number) => void;
  /** The audio player, shown under the heading. */
  player?: ReactNode;
}

const roleColour = (roles: RoleLabels, role: string | undefined) =>
  role && roles[role]?.analysed ? "bg-primary-chart" : "bg-speaker-students";

export function ReportTimeline({
  heading,
  utterances,
  roles,
  durationMs,
  removedSilence,
  phases,
  evidence,
  dimensionName,
  currentMs,
  onSeek,
  player,
}: ReportTimelineProps) {
  const bars = useMemo(
    () => buildBars(utterances, removedSilence, durationMs, BAR_COUNT),
    [utterances, removedSilence, durationMs],
  );
  const shares = useMemo(() => talkShares(utterances), [utterances]);
  const silenceMs = totalMs(removedSilence);
  const tickTimes = ticks(durationMs);

  const seekFromClick = (event: MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    if (box.width <= 0) return;
    onSeek(Math.round(((event.clientX - box.left) / box.width) * durationMs));
  };

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {heading}
        <ul aria-label="Legend" className="m-0 flex list-none flex-wrap gap-4 p-0 text-small text-ink-2">
          {shares.map(({ role, share }) => (
            <li key={role} className="flex items-center gap-1.5">
              <span aria-hidden="true" className={cx("h-2.5 w-2.5 rounded-sm", roleColour(roles, role))} />
              {roles[role]?.label ?? role}, {formatPercent(share)} of speech
            </li>
          ))}
          {silenceMs > 0 && (
            <li className="flex items-center gap-1.5">
              <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-line-input" />
              Silence removed, {formatMinutes(silenceMs)}
            </li>
          )}
        </ul>
      </div>

      {player}

      <div className="overflow-x-auto">
        <div className="flex min-w-[680px] flex-col gap-1.5">
          {phases && phases.length > 0 && (
            <ol aria-label="Phases" className="m-0 flex list-none gap-0.5 p-0 text-caption text-ink-2">
              {phases.map((phase, i) => (
                <li
                  key={`${phase.name}-${phase.start_ms}`}
                  title={`${phase.name}, ${formatClock(phase.start_ms)} to ${formatClock(phase.end_ms)}`}
                  className={cx(
                    "overflow-hidden whitespace-nowrap px-2 py-[5px]",
                    i % 2 ? "bg-fill-2" : "bg-fill",
                    i === 0 && "rounded-l-md",
                    i === phases.length - 1 && "rounded-r-md",
                  )}
                  style={{ width: `${percentAt(phase.end_ms - phase.start_ms, durationMs)}%` }}
                >
                  {phase.name}
                </li>
              ))}
            </ol>
          )}

          <div className="relative pt-[26px]" data-testid="timeline-track">
            {evidence.map((quote, i) => (
              <button
                key={`${quote.utterance_id}-${i}`}
                type="button"
                data-pin={i + 1}
                aria-label={`Play evidence ${i + 1} from ${formatClock(quote.start_ms)}`}
                onClick={() => onSeek(quote.start_ms)}
                className="absolute top-0 z-10 flex -translate-x-1/2 flex-col items-center rounded-full"
                style={{ left: `${percentAt(quote.start_ms, durationMs)}%` }}
              >
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink text-2xs font-bold text-surface">
                  {i + 1}
                </span>
                <span aria-hidden="true" className="h-1.5 w-px bg-ink" />
              </button>
            ))}
            {currentMs !== null && (
              <div
                aria-hidden="true"
                data-testid="playhead"
                className="pointer-events-none absolute bottom-0 top-[26px] z-[1] w-0.5 -translate-x-1/2 rounded-xs bg-ink"
                style={{ left: `${percentAt(currentMs, durationMs)}%` }}
              />
            )}
            <div
              role="img"
              aria-label="Speech over time coloured by speaker, with removed silence in grey. Click to play from a point."
              onClick={seekFromClick}
              className="flex h-16 cursor-pointer items-center gap-px rounded-md bg-surface-faint"
            >
              {bars.map((bar, i) => (
                <div
                  key={i}
                  data-kind={bar.kind}
                  className={cx(
                    "flex-1 rounded-[1px]",
                    bar.kind === "speech"
                      ? roleColour(roles, bar.role)
                      : bar.kind === "silence"
                        ? "bg-line-input"
                        : "bg-track",
                  )}
                  style={{ height: bar.height }}
                />
              ))}
            </div>
          </div>

          <div aria-hidden="true" className="relative h-4 text-xs text-muted-2">
            {tickTimes.map((t) => (
              <span
                key={t}
                className={cx("absolute", t > 0 && "-translate-x-1/2")}
                style={{ left: `${percentAt(t, durationMs)}%` }}
              >
                {formatClock(t)}
              </span>
            ))}
            <span className="absolute right-0">{formatClock(durationMs)}</span>
          </div>
        </div>
      </div>

      <p className="m-0 text-small text-muted">
        {dimensionName ? (
          <>
            Numbered markers show the evidence for <strong className="font-semibold text-ink">{dimensionName}</strong>
            .{" "}
          </>
        ) : null}
        Times refer to the original recording.
      </p>
    </div>
  );
}
