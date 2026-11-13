// Report header (UI v2, docs/design/v2/03-lesson-report.png): breadcrumb, the person's initials, the title with a
// "1 score disputed" badge, the details list (who, when, length and speech, rubric) and the actions beside it.

import type { ReactNode } from "react";

import { Avatar } from "../../design";
import { formatClock } from "../transcript";
import { formatIst, formatMinutes, joinList } from "./format";
import type { Labels, ReportRecording, RubricRef } from "./types";

export interface ReportHeaderProps {
  recording: ReportRecording;
  labels: Labels;
  /** The rubric the analysis used; omitted while there is no analysis yet. */
  rubric?: RubricRef;
  /** Link for the rubric version; without it the rubric is plain text (there is no rubric page yet). */
  rubricHref?: (rubric: RubricRef) => string;
  /** Controls on the right of the title (the analysis picker, the "More actions" menu). */
  actions?: ReactNode;
  /** Link for the breadcrumb's list page. Default /recordings. */
  listHref?: string;
  /** Scores with a dispute waiting, for the badge next to the title. */
  disputed?: number;
}

function Detail({ term, children }: { term: ReactNode; children: ReactNode }) {
  return (
    <div className="flex gap-1.5">
      <dt className="text-muted-2">{term}</dt>
      <dd className="m-0 font-medium">{children}</dd>
    </div>
  );
}

export function ReportHeader({
  recording,
  labels,
  rubric,
  rubricHref,
  actions,
  listHref = "/recordings",
  disputed = 0,
}: ReportHeaderProps) {
  const length = [
    formatMinutes(recording.duration_ms),
    recording.speech_ms === null ? null : `${formatMinutes(recording.speech_ms)} of speech`,
  ].filter(Boolean);
  return (
    <header className="flex flex-col gap-3">
      <nav aria-label="Breadcrumb" className="text-sm">
        <ol className="m-0 flex list-none gap-1.5 p-0 text-muted">
          <li>
            <a href={listHref} className="no-underline">
              {labels.recording_plural}
            </a>
          </li>
          <li aria-hidden="true">/</li>
          <li aria-current="page">{recording.type_label}</li>
        </ol>
      </nav>
      <div className="flex flex-wrap items-start lg:flex-nowrap justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <Avatar name={recording.person.name} size={44} className="mt-0.5 shrink-0" />
          <div className="flex min-w-0 flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <h1 className="m-0 text-title font-bold text-ink">{recording.title}</h1>
              {disputed > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-warning-tint px-2.5 py-0.5 text-small font-semibold text-warning-ink">
                  <span aria-hidden="true" className="size-1.5 rounded-full bg-warning" />
                  {disputed} {disputed === 1 ? "score" : "scores"} disputed
                </span>
              )}
            </div>
            <dl className="m-0 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
              <Detail term={labels.person}>
                {recording.person.name}
                {recording.person.unit ? `, ${recording.person.unit}` : ""}
              </Detail>
              <Detail term="Recorded">
                <time dateTime={recording.recorded_at}>{formatIst(recording.recorded_at)}</time>
                <span className="sr-only"> India Standard Time</span>
              </Detail>
              <Detail term="Length">
                {length.join(", ")}
                {recording.languages.length ? ` (${joinList(recording.languages)})` : ""}
                <span className="sr-only">, {formatClock(recording.duration_ms)}</span>
              </Detail>
              {rubric && (
                <Detail term="Rubric">
                  {rubricHref ? (
                    <a href={rubricHref(rubric)}>
                      {rubric.name} v{rubric.version}
                    </a>
                  ) : (
                    <>
                      {rubric.name} v{rubric.version}
                    </>
                  )}
                </Detail>
              )}
            </dl>
          </div>
        </div>
        {actions && <div className="flex min-w-0 max-w-full shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
