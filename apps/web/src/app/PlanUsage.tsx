// The plan block at the foot of the menu (UI v2, docs/design/v2/*.png): this month's audio hours, for
// owners and admins. Hours are measured audio (GET /v1/usage). With no allowance agreed yet, it shows the hours used
// without a limit rather than an invented one (golden rule 6). Hidden while loading or on error: it is not worth an
// error message of its own.

import type { UsageSummary } from "../api/types";
import { ProgressBar, cx, type ProgressTone } from "../design";
import { formatHours } from "./format";

const TONES: Record<NonNullable<UsageSummary["state"]>, ProgressTone> = {
  ok: "primary",
  warning: "primary",
  blocked: "danger",
  overage: "danger",
};

export function PlanUsage({ usage }: { usage: UsageSummary }) {
  const used = formatHours(usage.used_hours);
  const allowance = usage.allowance_hours;
  const amount = allowance === null ? `${used} h` : `${used} / ${formatHours(allowance)} h`;
  const summary =
    allowance === null
      ? `${used} audio ${used === "1" ? "hour" : "hours"} this month`
      : `${used} of ${formatHours(allowance)} audio hours used`;
  const alert = usage.state === "warning" || usage.state === "blocked" || usage.state === "overage";
  return (
    <section aria-label="Plan usage" className="flex flex-col gap-2 rounded-card bg-surface-subtle px-3 py-3">
      <p className="m-0 flex justify-between gap-2 text-sm">
        <span className="font-semibold text-ink">Audio this month</span>
        <span className="tabular-nums text-ink-2">
          <span aria-hidden="true">{amount}</span>
          <span className="sr-only">{summary}</span>
        </span>
      </p>
      {allowance !== null && (
        <ProgressBar
          value={Math.min(usage.used_hours, allowance)}
          max={allowance}
          label="Audio hours this month"
          valueText={summary}
          tone={usage.state ? TONES[usage.state] : "primary"}
        />
      )}
      <p className="m-0 text-caption text-muted">Resets on {formatResetDay(usage.resets_at)}</p>
      {alert && usage.message && (
        <p
          className={cx(
            "m-0 text-caption font-semibold",
            usage.state === "warning" ? "text-warning-ink" : "text-danger",
          )}
        >
          {usage.message}
        </p>
      )}
    </section>
  );
}

/** "1 November", in India time (the app shows Asia/Kolkata). */
function formatResetDay(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "long", timeZone: "Asia/Kolkata" }).format(
    new Date(iso),
  );
}
