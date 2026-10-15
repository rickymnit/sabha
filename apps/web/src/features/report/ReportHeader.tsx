// Report header (Analysis.dc.html:78-96): breadcrumb, title, details list and the export and share actions.

import type { ReactNode } from "react";

import { Button, PageHeader } from "../../design";
import { formatClock } from "../transcript";
import { formatIst, formatMinutes, joinList } from "./format";
import type { Labels, ReportRecording, RubricRef } from "./types";

export interface ReportHeaderProps {
  recording: ReportRecording;
  labels: Labels;
  /** The rubric the analysis used; omitted while there is no analysis yet. */
  rubric?: RubricRef;
  /** Link for the rubric version. Default /rubrics/{id}. */
  rubricHref?: (rubric: RubricRef) => string;
  /** Show the Export PDF and Share placeholders (only when there is a report to export). */
  showActions?: boolean;
  /** Link for the breadcrumb's list page. Default /recordings. */
  listHref?: string;
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
  rubricHref = (r) => `/rubrics/${encodeURIComponent(r.id)}`,
  showActions = false,
  listHref = "/recordings",
}: ReportHeaderProps) {
  const speech = [
    recording.speech_ms === null ? null : formatMinutes(recording.speech_ms),
    recording.languages.length ? joinList(recording.languages) : null,
  ].filter(Boolean);
  return (
    <PageHeader
      breadcrumbs={[{ label: labels.recording_plural, href: listHref }, { label: recording.type_label }]}
      title={recording.title}
      meta={
        <dl className="m-0 mt-1 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
          <Detail term={labels.person}>
            {recording.person.name}, {recording.person.unit}
          </Detail>
          <Detail term="Recorded">
            <time dateTime={recording.recorded_at}>{formatIst(recording.recorded_at)}</time>
            <span className="sr-only"> India Standard Time</span>, {formatClock(recording.duration_ms)}
          </Detail>
          {speech.length > 0 && <Detail term="Speech">{speech.join(", ")}</Detail>}
          {rubric && (
            <Detail term="Rubric">
              <a href={rubricHref(rubric)}>
                {rubric.name} v{rubric.version}
              </a>
            </Detail>
          )}
        </dl>
      }
      actions={
        showActions && (
          <>
            {/* Placeholders: export (P7) and sharing are not built yet. */}
            <Button variant="secondary" disabled title="Not available yet">
              Export PDF
            </Button>
            <Button disabled title="Not available yet">
              Share with {labels.person.toLowerCase()}
            </Button>
          </>
        )
      }
    />
  );
}
