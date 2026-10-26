import type { AnalysisVersion } from "../../api/types";
import { formatDateTime } from "../../app/format";

/** "26 Oct 2026, 10:42 · rubric v0.2 (latest)": a version in the picker and the earlier-version banner. */
export function versionLabel(v: AnalysisVersion, latest: boolean): string {
  return `${formatDateTime(v.created_at)} · rubric v${v.rubric_version}${latest ? " (latest)" : ""}`;
}
