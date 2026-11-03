// Rubric score list and the selected dimension's detail (Analysis.dc.html:187-246). Both take only verified
// dimensions; `visibleDimensions` in RecordingReport filters the payload before anything reaches them.

import { useId } from "react";

import { Button, ScoreBar, ScoreChip, cx } from "../../design";
import { formatClock } from "../transcript";
import { formatPercent } from "./format";
import { CheckIcon, SmallGoIcon, SmallPlayIcon } from "./icons";
import { useSeekMode } from "./seekMode";
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
}: RubricAccordionProps) {
  const headingId = useId();
  const mode = useSeekMode();
  return (
    <section
      aria-labelledby={headingId}
      className="min-w-0 overflow-hidden rounded-panel border border-line bg-surface"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line-subtle px-5 py-3.5">
        <h2 id={headingId} className="m-0 text-lg font-semibold">
          Rubric scores
        </h2>
        <span className="text-small text-muted">
          Every score quotes the {recordingWord}; quotes are checked against the transcript
        </span>
      </div>
      {dimensions.length === 0 ? (
        <p className="m-0 px-5 py-4 text-sm text-muted">No scores could be checked against the transcript.</p>
      ) : (
        <ul className="m-0 list-none p-0">
          {dimensions.map((d) => {
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
                    {d.suggestion && (
                      <p className="m-0 rounded-card bg-primary-tint-subtle px-4 py-3 text-primary-hover">
                        <span className="font-semibold">Try next time:</span> {d.suggestion}
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
