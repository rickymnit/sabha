// Rubric score list and the selected dimension's detail (Analysis.dc.html:187-246). Both take only verified
// dimensions; `visibleDimensions` in RecordingReport filters the payload before anything reaches them.

import { useId } from "react";

import { Button, ScoreBar, ScoreChip, cx } from "../../design";
import { formatClock } from "../transcript";
import { formatPercent } from "./format";
import { CheckIcon, SmallPlayIcon } from "./icons";
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
              <span className="font-semibold">Reviewed:</span> score set to {override.score} by a{" "}
              {override.reviewer_role} (AI score was {dimension.score}). {override.note}
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
                  icon={<SmallPlayIcon />}
                  aria-label={`Play evidence ${i + 1} from ${time}`}
                  onClick={() => onSeek(e.start_ms)}
                  className="flex-none px-3 text-sm"
                >
                  {time}
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
        {onDispute && (
          <Button variant="secondary" onClick={onDispute}>
            Dispute this score
          </Button>
        )}
        <span className="text-small text-muted">{provenance}</span>
      </div>
    </section>
  );
}
