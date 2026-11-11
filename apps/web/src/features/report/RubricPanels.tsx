// Rubric score list and the selected dimension's detail (Analysis.dc.html:187-246). Both take only verified
// dimensions; `visibleDimensions` in RecordingReport filters the payload before anything reaches them.

import { useId } from "react";

import { Button, ScoreBar, ScoreChip, cx, scoreBand } from "../../design";
import { formatClock } from "../transcript";
import { formatPercent } from "./format";
import { CheckIcon, SmallGoIcon, SmallPauseIcon, SmallPlayIcon } from "./icons";
import { usePlayingFrom, useSeekMode } from "./seekMode";
import { displayedScore, type VerifiedDimension } from "./types";

export interface RubricScoreListProps {
  dimensions: readonly VerifiedDimension[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export function RubricScoreList({ dimensions, selectedKey, onSelect }: RubricScoreListProps) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-[1_1_300px] flex-col gap-1.5 rounded-panel border border-line bg-surface p-4"
    >
      <h2 id={headingId} className="mx-1 mb-1.5 mt-0 text-lg font-semibold">
        Rubric scores
      </h2>
      {dimensions.length === 0 ? (
        <p className="m-1 text-sm text-muted">No scores could be checked against the transcript.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
          {dimensions.map((d) => {
            const selected = d.key === selectedKey;
            return (
              <li key={d.key}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onSelect(d.key)}
                  className={cx(
                    "flex min-h-12 w-full items-center justify-between gap-3 rounded-seg-outer border px-3 py-2 text-left text-ink",
                    selected
                      ? "border-primary bg-primary-tint-subtle"
                      : "border-line-subtle bg-surface hover:bg-surface-subtle",
                  )}
                >
                  <span className="flex flex-col">
                    <span className={selected ? "font-semibold" : "font-medium"}>{d.name}</span>
                    <span className="text-caption text-muted">Weight {formatPercent(d.weight)}</span>
                  </span>
                  <span className="flex items-center gap-2">
                    {d.override && <span className="text-caption font-semibold text-primary-hover">Reviewed</span>}
                    <ScoreChip score={displayedScore(d)} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export interface DimensionDetailProps {
  dimension: VerifiedDimension;
  /** Role label of the speaker of each quote (from the transcript), in evidence order. */
  speakers: readonly (string | undefined)[];
  onSeek: (ms: number) => void;
  /** "Scored by model ..., rubric ..." line. */
  provenance: string;
  /** Opens the dispute dialog; undefined when this viewer may not dispute (P6.7). */
  onDispute?: () => void;
}

export function DimensionDetail({ dimension, speakers, onSeek, provenance, onDispute }: DimensionDetailProps) {
  const headingId = useId();
  const mode = useSeekMode();
  const override = dimension.override;
  return (
    <section
      aria-labelledby={headingId}
      data-dimension={dimension.key}
      className="flex min-w-0 flex-[999_1_480px] flex-col gap-4 rounded-panel border border-line bg-surface px-6 py-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-2">
          <h2 id={headingId} className="m-0 text-2xl font-semibold tracking-[-0.01em]">
            {dimension.name}
          </h2>
          <ScoreBar score={displayedScore(dimension)} />
          {override && (
            <p className="m-0 text-small text-ink-2" data-testid="override-note">
              <span className="font-semibold">Reviewed:</span> score set to {override.score} by{" "}
              {/^[aeiou]/i.test(override.reviewer_role) ? "an" : "a"} {override.reviewer_role} (AI score was{" "}
              {dimension.score}). {override.note}
            </p>
          )}
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-success-tint px-2.5 py-[5px] text-small font-semibold text-success">
          <CheckIcon />
          Quotes verified in transcript
        </span>
      </div>
      <p className="m-0 max-w-[72ch] text-ink-2">{dimension.rationale}</p>

      <div className="flex flex-col gap-2.5">
        <h3 className="m-0 text-table font-semibold">Evidence</h3>
        <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
          {dimension.evidence.map((e, i) => {
            const time = formatClock(e.start_ms);
            const who = speakers[i];
            return (
              <li
                key={`${e.utterance_id}-${i}`}
                data-evidence={i + 1}
                className="flex items-start gap-3 rounded-card border border-track bg-surface-subtle px-3.5 py-3"
              >
                <span
                  aria-hidden="true"
                  className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full bg-ink text-xs font-bold text-surface"
                >
                  {i + 1}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <q className="text-ink [quotes:none]">{e.quote}</q>
                  <span className="text-small text-muted">{who ? `${who}, ${time}` : time}</span>
                </div>
                <Button
                  variant="secondary"
                  icon={mode === "go" ? <SmallGoIcon /> : <SmallPlayIcon />}
                  aria-label={
                    mode === "go"
                      ? `Go to evidence ${i + 1} at ${time} in the transcript`
                      : `Play evidence ${i + 1} from ${time}`
                  }
                  onClick={() => onSeek(e.start_ms)}
                  className="flex-none px-3 text-sm"
                >
                  {mode === "go" ? `Go to ${time}` : time}
                </Button>
              </li>
            );
          })}
        </ol>
      </div>

      {dimension.suggestion && (
        <div className="flex flex-col gap-1.5 rounded-card border border-primary-tint-strong bg-primary-tint-subtle px-4 py-3.5">
          <h3 className="m-0 text-table font-semibold text-primary-hover">Try next time</h3>
          <p className="m-0 max-w-[72ch] text-ink">{dimension.suggestion}</p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-track pt-4">
        {/* Only people who may dispute see the button; a disabled one would read as broken. */}
        {dimension.dispute_open ? (
          <span className="rounded-full bg-warning-tint px-2.5 py-0.5 text-small font-semibold text-warning-ink">
            Dispute waiting for a reviewer
          </span>
        ) : (
          onDispute && (
            <Button variant="secondary" onClick={onDispute}>
              Dispute this score
            </Button>
          )
        )}
        <span className="text-small text-muted">{provenance}</span>
      </div>
    </section>
  );
}

export interface RubricAccordionProps {
  dimensions: readonly VerifiedDimension[];
  openKey: string | null;
  onToggle: (key: string) => void;
  /** Role label of each quote's speaker, for the open dimension, in evidence order. */
  speakers: readonly (string | undefined)[];
  onSeek: (ms: number) => void;
  provenance: string;
  /** The rubric's level descriptions for a dimension (UI v2 "Level 2: where this lesson is"), when loaded. */
  levels?: (key: string) => readonly { level: number; description: string }[] | undefined;
  /** "Dispute this score" for the person analysed, "Change score, with a note" for managers. */
  disputeLabel?: string;
  /** Who raised an open dispute, for "Weight 20%, disputed by Anjali". */
  disputedBy?: string;
  /** The tenant's word for the recording, for "where this lesson is". */
  recordingWord: string;
  onDispute?: () => void;
  /**
   * UI v2 sales call report ("Where the points were lost"): rows sorted by how much each pulled the overall score
   * down, (5 - score) x its share of the verified weight, with the two biggest marked "Fix first".
   */
  pointsLost?: boolean;
  /** The overall score shown above, so "2.9 of 5 points lost" matches it (reviewers' scores included). */
  overall?: number | null;
}

/** "1.0", "0.75", "0.5", "0": as the design writes points lost. */
function formatLost(lost: number): string {
  return lost >= 1 ? lost.toFixed(1) : String(Math.round(lost * 100) / 100);
}

const LOST_INK = { low: "text-danger", mid: "text-warning-ink", good: "text-success" } as const;

/** Points each dimension took off the overall score: (5 - score) x its share of the verified weight. */
function pointsLostBy(dimensions: readonly VerifiedDimension[]): Map<string, { lost: number; share: number }> {
  const total = dimensions.reduce((sum, d) => sum + d.weight, 0);
  return new Map(
    dimensions.map((d) => {
      const share = total > 0 ? d.weight / total : 0;
      return [d.key, { lost: (5 - displayedScore(d)) * share, share }];
    }),
  );
}

/**
 * UI v2 rubric scores (docs/design/v2/03-lesson-report.png): one row per verified dimension with its weight, five
 * dashes and the score; the open row shows the reasoning, where this score sits on the rubric and the next level,
 * the numbered evidence, "Try next time" and the dispute button.
 */
export function RubricAccordion({
  dimensions,
  openKey,
  onToggle,
  speakers,
  onSeek,
  provenance,
  levels,
  disputeLabel = "Dispute this score",
  disputedBy,
  recordingWord,
  onDispute,
  pointsLost = false,
  overall,
}: RubricAccordionProps) {
  const headingId = useId();
  const mode = useSeekMode();
  const playingFrom = usePlayingFrom();
  const lost = pointsLostBy(dimensions);
  const lostOf = (key: string) => lost.get(key)?.lost ?? 0;
  const rows = pointsLost ? [...dimensions].sort((a, b) => lostOf(b.key) - lostOf(a.key)) : dimensions;
  const mostLost = Math.max(0.0001, ...rows.map((d) => lostOf(d.key)));
  const fixFirst = new Set(
    rows
      .filter((d) => lostOf(d.key) > 0)
      .slice(0, 2)
      .map((d) => d.key),
  );
  const totalLost = overall != null ? 5 - overall : rows.reduce((sum, d) => sum + lostOf(d.key), 0);
  return (
    <section
      aria-labelledby={headingId}
      className="min-w-0 overflow-hidden rounded-panel border border-line bg-surface"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line-subtle px-5 py-3.5">
        {pointsLost ? (
          <>
            <div className="flex flex-col gap-0.5">
              <h2 id={headingId} className="m-0 text-lg font-semibold">
                Where the points were lost
              </h2>
              <span className="text-small text-muted">
                Sorted by how much each rubric point pulled the overall score down
              </span>
            </div>
            <span className="text-small text-ink-2" data-testid="points-lost-total">
              {totalLost.toFixed(1)} of 5 points lost in total
            </span>
          </>
        ) : (
          <>
            <h2 id={headingId} className="m-0 text-lg font-semibold">
              Rubric scores
            </h2>
            <span className="text-small text-muted">
              Every score quotes the {recordingWord}; quotes are checked against the transcript
            </span>
          </>
        )}
      </div>
      {pointsLost && dimensions.length > 0 && (
        <div
          aria-hidden="true"
          className="hidden grid-cols-[minmax(0,1fr)_96px_minmax(180px,240px)_24px] gap-4 border-b border-line-subtle bg-surface-faint px-5 py-2 text-caption text-muted md:grid"
        >
          <span>Rubric point</span>
          <span>Score</span>
          <span>Points lost</span>
          <span />
        </div>
      )}
      {dimensions.length === 0 ? (
        <p className="m-0 px-5 py-4 text-sm text-muted">No scores could be checked against the transcript.</p>
      ) : (
        <ul className="m-0 list-none p-0">
          {rows.map((d) => {
            const open = d.key === openKey;
            const score = displayedScore(d);
            const scale = levels?.(d.key) ?? [];
            const here = scale.find((l) => l.level === score);
            const next = scale.find((l) => l.level === score + 1);
            const panelId = `dimension-${d.key}`;
            return (
              <li
                key={d.key}
                data-dimension={d.key}
                className={cx("border-b border-line-subtle last:border-b-0", open && "bg-primary-tint-subtle/40")}
              >
                {pointsLost ? (
                  <button
                    type="button"
                    aria-expanded={open}
                    aria-controls={panelId}
                    onClick={() => onToggle(d.key)}
                    className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-5 py-3 text-left md:grid-cols-[minmax(0,1fr)_96px_minmax(180px,240px)_24px]"
                  >
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-ink">{d.name}</span>
                        {fixFirst.has(d.key) && (
                          <span className="rounded bg-ink px-1.5 py-0.5 text-2xs font-semibold text-surface">
                            Fix first
                          </span>
                        )}
                        {d.override && <span className="text-caption font-semibold text-primary-hover">Reviewed</span>}
                        {d.dispute_open && (
                          <span className="text-caption font-semibold text-warning-ink">Disputed</span>
                        )}
                      </span>
                      {!open && <span className="line-clamp-1 text-small text-muted">{d.rationale}</span>}
                    </span>
                    <span className="flex items-center gap-2 justify-self-end md:justify-self-start">
                      <ScoreBar score={score} hideValue shape="dot" />
                      <span className={cx("text-sm font-semibold tabular-nums", LOST_INK[scoreBand(score)])}>
                        {score}/5
                      </span>
                    </span>
                    <span className="col-span-2 flex items-center gap-3 md:col-span-1">
                      <span aria-hidden="true" className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-track">
                        <span
                          className={cx(
                            "block h-full rounded-full",
                            fixFirst.has(d.key) ? "bg-danger-bar" : "bg-danger-bar/45",
                          )}
                          style={{ width: `${(lostOf(d.key) / mostLost) * 100}%` }}
                        />
                      </span>
                      <span className="shrink-0 whitespace-nowrap text-small">
                        <span className="font-semibold tabular-nums text-ink">
                          {lostOf(d.key) > 0 ? "−" : ""}
                          {formatLost(lostOf(d.key))}
                        </span>{" "}
                        <span className="text-muted">counts {formatPercent(lost.get(d.key)?.share ?? d.weight)}</span>
                      </span>
                    </span>
                    <span
                      aria-hidden="true"
                      className={cx("hidden text-muted transition-transform md:inline", open && "rotate-180")}
                    >
                      ⌄
                    </span>
                  </button>
                ) : (
                  <button
                    type="button"
                    aria-expanded={open}
                    aria-controls={panelId}
                    onClick={() => onToggle(d.key)}
                    className="flex min-h-[56px] w-full items-center justify-between gap-3 px-5 py-2.5 text-left"
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="font-semibold text-ink">{d.name}</span>
                      <span className="text-caption text-muted">
                        Weight {formatPercent(d.weight)}
                        {d.dispute_open ? `, disputed${disputedBy ? ` by ${disputedBy}` : ""}` : ""}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-3">
                      {d.override && <span className="text-caption font-semibold text-primary-hover">Reviewed</span>}
                      <ScoreBar score={score} hideValue className="hidden sm:inline-flex" />
                      <ScoreChip score={score} />
                      <span aria-hidden="true" className={cx("text-muted transition-transform", open && "rotate-180")}>
                        ⌄
                      </span>
                    </span>
                  </button>
                )}
                {open && (
                  <div id={panelId} className="flex flex-col gap-4 px-5 pb-5">
                    {d.override && (
                      <p className="m-0 text-small text-ink-2" data-testid="override-note">
                        <span className="font-semibold">Reviewed:</span> score set to {d.override.score} by{" "}
                        {/^[aeiou]/i.test(d.override.reviewer_role) ? "an" : "a"} {d.override.reviewer_role} (AI score
                        was {d.score}). {d.override.note}
                      </p>
                    )}
                    <p className="m-0 max-w-[72ch] text-ink-2">{d.rationale}</p>
                    {(here || next) && (
                      <div className="grid gap-3 sm:grid-cols-2">
                        {here && (
                          <div
                            className={cx(
                              "rounded-card px-4 py-3",
                              score < 3 ? "bg-danger-tint" : score < 4 ? "bg-warning-tint" : "bg-success-tint",
                            )}
                          >
                            <p className="m-0 text-small font-semibold text-ink">
                              Level {here.level}: where this {recordingWord} is
                            </p>
                            <p className="m-0 mt-1 text-sm text-ink-2">{here.description}</p>
                          </div>
                        )}
                        {next && (
                          <div className="rounded-card border border-primary-border bg-surface px-4 py-3">
                            <p className="m-0 text-small font-semibold text-primary-hover">
                              Level {next.level}: what the next step looks like
                            </p>
                            <p className="m-0 mt-1 text-sm text-ink-2">{next.description}</p>
                          </div>
                        )}
                      </div>
                    )}
                    <ol aria-label="Evidence" className="m-0 flex list-none flex-col gap-2.5 p-0">
                      {d.evidence.map((e, i) => {
                        const time = formatClock(e.start_ms);
                        const who = speakers[i];
                        return (
                          <li
                            key={`${e.utterance_id}-${i}`}
                            data-evidence={i + 1}
                            className="flex items-start gap-3 rounded-card border border-track bg-surface px-3.5 py-3"
                          >
                            <span
                              aria-hidden="true"
                              className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full bg-ink text-xs font-bold text-surface"
                            >
                              {i + 1}
                            </span>
                            <div className="flex min-w-0 flex-1 flex-col gap-1">
                              <q className="text-ink [quotes:none]">{e.quote}</q>
                              {who && <span className="text-small text-muted">{who}</span>}
                            </div>
                            <Button
                              variant="secondary"
                              icon={
                                mode === "go" ? (
                                  <SmallGoIcon />
                                ) : playingFrom === e.start_ms ? (
                                  <SmallPauseIcon />
                                ) : (
                                  <SmallPlayIcon />
                                )
                              }
                              aria-label={
                                mode === "go"
                                  ? `Go to evidence ${i + 1} at ${time} in the transcript`
                                  : playingFrom === e.start_ms
                                    ? `Pause evidence ${i + 1}, playing from ${time}`
                                    : `Play evidence ${i + 1} from ${time}`
                              }
                              onClick={() => onSeek(e.start_ms)}
                              className="flex-none px-3 text-sm"
                            >
                              {mode === "go" ? `Go to ${time}` : time}
                            </Button>
                          </li>
                        );
                      })}
                    </ol>
                    {d.suggestion && (
                      <p className="m-0 rounded-card bg-primary-tint-subtle px-4 py-3 text-primary-hover">
                        <span className="font-semibold">{pointsLost ? "Next time:" : "Try next time:"}</span>{" "}
                        {d.suggestion}
                      </p>
                    )}
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                      {d.dispute_open ? (
                        <span className="rounded-full bg-warning-tint px-2.5 py-0.5 text-small font-semibold text-warning-ink">
                          Dispute waiting for a reviewer
                        </span>
                      ) : (
                        onDispute && (
                          <Button variant="secondary" onClick={onDispute}>
                            {disputeLabel}
                          </Button>
                        )
                      )}
                      <span className="text-small text-muted">{provenance}</span>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
