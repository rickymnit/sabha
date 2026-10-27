// The plan block at the foot of the menu (docs/design/01-overview.png): the plan and this month's audio hours, for
// owners and admins. Hours are measured audio (GET /v1/usage). With no allowance agreed yet, it shows the hours used
// without a limit rather than an invented one (golden rule 6). Hidden while loading or on error: it is not worth an
// error message of its own.

import type { UsageSummary } from "../api/types";
import { ProgressBar, cx, type ProgressTone } from "../design";
import { capitalise, formatHours } from "./format";

const TONES: Record<NonNullable<UsageSummary["state"]>, ProgressTone> = {
  ok: "primary",
  warning: "primary",
  blocked: "danger",
  overage: "danger",
};

export function PlanUsage({ usage }: { usage: UsageSummary }) {
  const used = formatHours(usage.used_hours);
  const allowance = usage.allowance_hours;
  const summary =
    allowance === null
      ? `${used} audio ${used === "1" ? "hour" : "hours"} this month`
      : `${used} of ${formatHours(allowance)} audio hours used`;
  const alert = usage.state === "warning" || usage.state === "blocked" || usage.state === "overage";
  return (
    <section aria-label="Plan usage" className="flex flex-col gap-2 rounded border border-line bg-surface px-3 py-2.5">
      <p className="m-0 text-sm font-semibold text-ink">{capitalise(usage.plan)} plan</p>
      {allowance !== null && (
        <ProgressBar
          value={Math.min(usage.used_hours, allowance)}
          max={allowance}
          label="Audio hours this month"
          valueText={summary}
          tone={usage.state ? TONES[usage.state] : "primary"}
        />
      )}
      <p className="m-0 text-caption text-muted-2">{summary}</p>
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
