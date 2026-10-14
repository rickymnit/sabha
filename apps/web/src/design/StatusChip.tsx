import type { ReactNode } from "react";

import { cx } from "./cx";
import type { RecordingStatus } from "./types";

// Main.dc.html:227-230. Failed and Uploading are not in the designs; they use the upload-row styles
// (Upload.dc.html:261, :264) as tokens.md "Status chips" suggests.
const styles: Record<RecordingStatus, { className: string; label: string }> = {
  analysed: { className: "bg-success-tint text-success", label: "Analysed" },
  transcribing: { className: "bg-primary-tint text-primary-hover", label: "Transcribing" },
  analysing: { className: "bg-primary-tint text-primary-hover", label: "Analysing" },
  "needs-review": { className: "bg-warning-tint text-warning-ink", label: "Needs review" },
  failed: { className: "bg-danger-tint text-danger", label: "Failed" },
  uploading: { className: "bg-primary-tint text-primary-hover", label: "Uploading" },
};

export interface StatusChipProps {
  status: RecordingStatus;
  /** Visible text; defaults to the English status name. The text, not the colour, carries the status. */
  children?: ReactNode;
  className?: string;
}

/** Pill with a 6px dot: 3px 9px padding, 12.5px / 600 (Main.dc.html:187). */
export function StatusChip({ status, children, className }: StatusChipProps) {
  const style = styles[status];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-[9px] py-[3px] text-small font-semibold",
        style.className,
        className,
      )}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
      {children ?? style.label}
    </span>
  );
}
