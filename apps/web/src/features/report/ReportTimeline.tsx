// Recording timeline (UI v2, docs/design/v2/03-lesson-report.png): the player and legend, phases, one lane for the
// analysed person's speech and one for everyone else, numbered evidence pins for the selected dimension, and the
// playhead. "Zoom to 10 min" shows ten minutes around the playhead (or the first pin); the arrows move the window.
// Times are on the original timeline (golden rule 4).

import { useMemo, useState, type MouseEvent, type ReactNode } from "react";

import { cx } from "../../design";
import { formatClock, type RoleLabels, type Utterance } from "../transcript";
import { formatMinutes, formatPercent, sentenceCase } from "./format";
import { laneSpans, percentAt, talkShares, ticks, totalMs, zoomWindow, type LaneSpan } from "./timeline";
import { useSeekMode } from "./seekMode";
import type { EvidenceQuote, Phase, TimeRange } from "./types";

const ZOOM_MS = 10 * 60_000;

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
  /** The tenant's word for the recording, for "Whole lesson". */
  recordingWord?: string;
}

const roleColour = (roles: RoleLabels, role: string | undefined) =>
  role && roles[role]?.analysed ? "bg-speaker-staff" : "bg-speaker-other";

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
  recordingWord = "recording",
}: ReportTimelineProps) {
  const go = useSeekMode() === "go";
  const [zoomed, setZoomed] = useState(false);
  const [centre, setCentre] = useState<number | null>(null);
  const canZoom = durationMs > ZOOM_MS * 1.2;
  const view = zoomed
    ? zoomWindow(centre ?? currentMs ?? evidence[0]?.start_ms ?? 0, durationMs, ZOOM_MS)
    : { start_ms: 0, end_ms: durationMs };
  const span = Math.max(1, view.end_ms - view.start_ms);
  const at = (ms: number) => percentAt(ms - view.start_ms, span);
  const inView = (ms: number) => ms >= view.start_ms && ms <= view.end_ms;
  const isStaff = (role: string) => Boolean(roles[role]?.analysed);
  const lanes = useMemo(
    () => laneSpans(utterances, (role) => Boolean(roles[role]?.analysed), Math.max(1500, durationMs / 400)),
    [utterances, roles, durationMs],
  );
  const shares = useMemo(() => talkShares(utterances), [utterances]);
  const silenceMs = totalMs(removedSilence);
  const tickTimes = ticks(span).map((t) => view.start_ms + t);
  const staffLabel = Object.entries(roles).find(([, r]) => r.analysed)?.[1]?.label ?? "Staff";
  const otherLabels = [
    ...new Set(
      Object.entries(roles).flatMap(([key, r]) => (r.analysed || !shares.some((s) => s.role === key) ? [] : [r.label])),
    ),
  ];
  const othersLabel = otherLabels.length ? otherLabels.join(", ") : "Others";

  const seekFromClick = (event: MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    if (box.width <= 0) return;
    onSeek(Math.round(view.start_ms + ((event.clientX - box.left) / box.width) * span));
  };
  const move = (by: number) => setCentre(Math.min(durationMs, Math.max(0, (view.start_ms + view.end_ms) / 2 + by)));
  const lane = (spans: LaneSpan[], colour: string) =>
    spans
      .filter((x) => x.end_ms > view.start_ms && x.start_ms < view.end_ms)
      .map((x) => (
        <span
          key={x.start_ms}
          className={cx("absolute inset-y-0 rounded-[3px]", colour)}
          style={{ left: `${at(x.start_ms)}%`, width: `${Math.max(0.25, at(x.end_ms) - at(x.start_ms))}%` }}
        />
      ));

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {heading}
        <ul aria-label="Legend" className="m-0 flex list-none flex-wrap gap-4 p-0 text-small text-ink-2">
          {shares.map(({ role, share }) => (
            <li key={role} className="flex items-center gap-1.5">
              <span aria-hidden="true" className={cx("h-2.5 w-2.5 rounded-sm", roleColour(roles, role))} />
              {roles[role]?.label ?? role}, {formatPercent(share)}
              {isStaff(role) ? " of speech" : ""}
            </li>
          ))}
          {silenceMs > 0 && (
            <li className="flex items-center gap-1.5">
              <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-line-input" />
              Silence removed, {formatMinutes(silenceMs)}
            </li>
          )}
          {dimensionName && evidence.length > 0 && (
            <li className="flex items-center gap-1.5">
              <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-ink" />
              Evidence for {dimensionName}
            </li>
          )}
        </ul>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">{player}</div>
        {canZoom && (
          <div className="flex items-center gap-1.5">
            <div
              role="group"
              aria-label="Zoom"
              className="inline-flex rounded-md border border-line bg-surface-subtle p-0.5"
            >
              {[
                [false, `Whole ${recordingWord}`],
                [true, "Zoom to 10 min"],
              ].map(([value, text]) => (
                <button
                  key={String(value)}
                  type="button"
                  aria-pressed={zoomed === value}
                  onClick={() => {
                    setZoomed(value as boolean);
                    setCentre(null);
                  }}
                  className={cx(
                    "min-h-[36px] rounded px-3 text-small",
                    zoomed === value ? "bg-surface font-semibold text-ink shadow-sm" : "text-muted hover:text-ink",
                  )}
                >
                  {text as string}
                </button>
              ))}
            </div>
            {zoomed && (
              <>
                <button
                  type="button"
                  aria-label="Earlier"
                  disabled={view.start_ms <= 0}
                  onClick={() => move(-ZOOM_MS / 2)}
                  className="flex size-9 items-center justify-center rounded-md border border-line disabled:opacity-40"
                >
                  ‹
                </button>
                <button
                  type="button"
                  aria-label="Later"
                  disabled={view.end_ms >= durationMs}
                  onClick={() => move(ZOOM_MS / 2)}
                  className="flex size-9 items-center justify-center rounded-md border border-line disabled:opacity-40"
                >
                  ›
                </button>
              </>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {phases && phases.length > 0 && (
          <div className="ml-[76px] overflow-hidden">
            <ol aria-label="Phases" className="relative m-0 h-7 list-none p-0 text-caption text-ink-2">
              {phases
                .filter((phase) => phase.end_ms > view.start_ms && phase.start_ms < view.end_ms)
                .map((phase) => (
                  <li
                    key={`${phase.name}-${phase.start_ms}`}
                    title={`${sentenceCase(phase.name)}, ${formatClock(phase.start_ms)} to ${formatClock(phase.end_ms)}`}
                    className="absolute inset-y-0 overflow-hidden whitespace-nowrap rounded-md border-r-2 border-surface bg-fill px-2 py-[5px]"
                    style={{
                      left: `${at(Math.max(phase.start_ms, view.start_ms))}%`,
                      width: `${at(Math.min(phase.end_ms, view.end_ms)) - at(Math.max(phase.start_ms, view.start_ms))}%`,
                    }}
                  >
                    {sentenceCase(phase.name)}
                  </li>
                ))}
            </ol>
          </div>
        )}

        <div className="flex gap-3">
          <div
            aria-hidden="true"
            className="flex w-16 shrink-0 flex-col justify-end gap-2 pb-0.5 text-small font-semibold"
          >
            <span className="flex h-[18px] items-center text-primary">{staffLabel}</span>
            <span className="flex h-[18px] items-center text-warning">{othersLabel}</span>
          </div>
          <div className="relative min-w-0 flex-1 pt-[26px]" data-testid="timeline-track">
            {evidence.map((quote, i) =>
              inView(quote.start_ms) ? (
                <button
                  key={`${quote.utterance_id}-${i}`}
                  type="button"
                  data-pin={i + 1}
                  aria-label={
                    go
                      ? `Go to evidence ${i + 1} at ${formatClock(quote.start_ms)} in the transcript`
                      : `Play evidence ${i + 1} from ${formatClock(quote.start_ms)}`
                  }
                  onClick={() => onSeek(quote.start_ms)}
                  className="absolute top-0 z-10 flex -translate-x-1/2 flex-col items-center rounded-full"
                  style={{ left: `${at(quote.start_ms)}%` }}
                >
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink text-2xs font-bold text-surface">
                    {i + 1}
                  </span>
                  <span aria-hidden="true" className="h-1.5 w-px bg-ink" />
                </button>
              ) : null,
            )}
            {currentMs !== null && inView(currentMs) && (
              <div
                aria-hidden="true"
                data-testid="playhead"
                className="pointer-events-none absolute bottom-0 top-[26px] z-[1] w-0.5 -translate-x-1/2 rounded-xs bg-ink"
                style={{ left: `${at(currentMs)}%` }}
              />
            )}
            <div
              role="img"
              aria-label={`Who spoke when: ${staffLabel} in the top lane, ${othersLabel.toLowerCase()} below. Click to play from a point.`}
              onClick={seekFromClick}
              className="flex cursor-pointer flex-col gap-2"
            >
              <div className="relative h-[18px] rounded-[3px] bg-surface-faint">
                {lane(lanes.staff, "bg-speaker-staff")}
              </div>
              <div className="relative h-[18px] rounded-[3px] bg-surface-faint">
                {lane(lanes.others, "bg-speaker-other")}
              </div>
            </div>
          </div>
        </div>

        <div aria-hidden="true" className="relative ml-[76px] h-4 text-xs text-muted-2">
          {tickTimes.map((t) => (
            <span
              key={t}
              className={cx("absolute", t > view.start_ms && "-translate-x-1/2")}
              style={{ left: `${at(t)}%` }}
            >
              {formatClock(t)}
            </span>
          ))}
          <span className="absolute right-0">{formatClock(view.end_ms)}</span>
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
