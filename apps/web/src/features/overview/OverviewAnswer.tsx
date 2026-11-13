// The top of the Overview, read in a few seconds (manager's feedback, 2026-11-13): one sentence, three big cards
// (going well, needs work, do today) and the people from "needs help" to "good", each with one reason. Details stay
// one click away under "See all numbers". The words come from answer.ts, worked out in code.

import type { ReactNode } from "react";

import { Avatar, Icon, Skeleton, cx, type IconName, type ScoreBand } from "../../design";
import type { Labels } from "../report/types";
import { areaCards, overviewHeadline, personLines, RECENT_COUNT, type AreaCard, type PersonRow } from "./answer";
import type { OverviewStats } from "./types";

const DOT: Record<ScoreBand, string> = { low: "bg-danger-bar", mid: "bg-warning-bar", good: "bg-success-bar" };
const WORD: Record<ScoreBand, string> = { low: "text-danger", mid: "text-warning", good: "text-success" };
const PEOPLE_SHOWN = 6;

export interface OverviewAnswerProps {
  stats: OverviewStats;
  people: readonly PersonRow[] | undefined;
  labels: Labels;
  /** Things waiting for a decision from this person. */
  waiting: number;
  /** Opens a page in the app (keeps Ctrl-click for a new tab). */
  onOpen: (to: string) => void;
  /** Where "do today" goes: the reviews page for resolvers, else the inbox. */
  decisionsHref: string;
}

function BigCard({
  tone,
  icon,
  label,
  children,
  action,
}: {
  tone: "good" | "work" | "do";
  icon: IconName;
  label: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  const tones = {
    good: "border-success-tint bg-success-tint/50",
    work: "border-warning-tint bg-warning-tint/50",
    do: "border-primary-tint-strong bg-primary-tint-subtle",
  } as const;
  const ink = { good: "text-success", work: "text-warning-ink", do: "text-primary-hover" } as const;
  return (
    <section
      aria-label={label}
      className={cx("flex min-w-0 flex-col gap-2 rounded-panel border px-5 py-4", tones[tone])}
    >
      <span className={cx("flex items-center gap-1.5 text-small font-bold uppercase tracking-wide", ink[tone])}>
        <Icon name={icon} size={15} /> {label}
      </span>
      <div className="flex flex-1 flex-col gap-1">{children}</div>
      {action}
    </section>
  );
}

function Area({ area, empty }: { area: AreaCard | null; empty: string }) {
  if (!area) return <p className="m-0 text-md text-ink-2">{empty}</p>;
  return (
    <>
      <p className="m-0 text-xl font-bold leading-snug text-ink">{area.name}</p>
      <p className="m-0 text-sm text-ink-2">
        <span className={cx("font-semibold", WORD[area.band])}>{area.word}</span>
        <span className="text-muted">
          {" "}
          · {area.median.toFixed(1)} / 5 across {area.n}
        </span>
      </p>
    </>
  );
}

function Dots({ level, band }: { level: number; band: ScoreBand }) {
  const filled = Math.round(level);
  return (
    <span aria-hidden="true" className="flex gap-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={cx("size-2.5 rounded-full", i <= filled ? DOT[band] : "bg-fill-2")} />
      ))}
    </span>
  );
}

function CardLink({ to, onOpen, children }: { to: string; onOpen: (to: string) => void; children: ReactNode }) {
  return (
    <a
      href={to}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        onOpen(to);
      }}
      className="mt-1 inline-flex items-center gap-1 self-start text-sm font-semibold no-underline"
    >
      {children} <Icon name="chevronRight" size={14} />
    </a>
  );
}

export function OverviewAnswer({ stats, people, labels, waiting, onOpen, decisionsHref }: OverviewAnswerProps) {
  const headline = overviewHeadline(stats, people ?? [], labels);
  const { good, work } = areaCards(stats);
  const lines = personLines(people ?? []);
  const personWord = labels.person.toLowerCase();
  const recordings = labels.recording_plural.toLowerCase();
  return (
    <div className="flex flex-col gap-5">
      <section aria-label="In short" className="flex items-start gap-3">
        {headline.band && (
          <span aria-hidden="true" className={cx("mt-3 size-3.5 shrink-0 rounded-full", DOT[headline.band])} />
        )}
        <div className="flex flex-col gap-1">
          <p className="m-0 text-3xl font-bold text-ink">{headline.title}</p>
          {headline.detail && <p className="m-0 text-lg text-ink-2">{headline.detail}</p>}
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <BigCard tone="good" icon="check" label="Going well">
          <Area area={good} empty="Nothing stands out yet." />
        </BigCard>
        <BigCard
          tone="work"
          icon="alert"
          label="Needs work"
          action={
            work && (
              <CardLink to="/recordings?score=below_3" onOpen={onOpen}>
                See the {recordings} scored below 3
              </CardLink>
            )
          }
        >
          <Area area={work} empty="Nothing is below Fair. Well done." />
        </BigCard>
        <BigCard
          tone="do"
          icon="bell"
          label="Do today"
          action={
            waiting > 0 && (
              <CardLink to={decisionsHref} onOpen={onOpen}>
                Open them
              </CardLink>
            )
          }
        >
          {waiting > 0 ? (
            <>
              <p className="m-0 text-xl font-bold leading-snug text-ink">
                {waiting} {waiting === 1 ? "thing needs" : "things need"} your decision
              </p>
              <p className="m-0 text-sm text-muted">Score reviews, failed uploads and follow-ups.</p>
            </>
          ) : (
            <p className="m-0 text-md text-ink-2">Nothing needs you today.</p>
          )}
        </BigCard>
      </div>

      <section aria-label={labels.person_plural} className="rounded-panel border border-line bg-surface">
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line-subtle px-5 py-3.5">
          <h2 className="m-0 text-lg font-semibold">How each {personWord} is doing</h2>
          <span className="text-small text-muted">
            Their last {RECENT_COUNT} {recordings}, lowest first
          </span>
        </div>
        {people === undefined ? (
          <div className="p-5">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : lines.length === 0 ? (
          <p className="m-0 px-5 py-4 text-sm text-muted">
            Once {recordings} are scored, each {personWord} shows here.
          </p>
        ) : (
          <ul className="m-0 list-none p-0">
            {lines.slice(0, PEOPLE_SHOWN).map((p) => (
              <li key={p.id} className="border-b border-line-subtle last:border-b-0">
                <a
                  href={`/recordings?person=${encodeURIComponent(p.id)}`}
                  onClick={(e) => {
                    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                    e.preventDefault();
                    onOpen(`/recordings?person=${encodeURIComponent(p.id)}`);
                  }}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-5 py-3 text-ink no-underline hover:bg-surface-faint"
                >
                  <span className="flex min-w-0 flex-[1_1_200px] items-center gap-3">
                    <Avatar name={p.name} size={32} />
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate font-semibold">{p.name}</span>
                      <span className="truncate text-small text-muted">{p.reason}</span>
                    </span>
                  </span>
                  <span className="flex items-center gap-3">
                    <Dots level={p.level} band={p.band} />
                    <span className={cx("w-[88px] text-sm font-semibold", WORD[p.band])}>{p.word}</span>
                    <span className="sr-only">{p.level.toFixed(1)} out of 5</span>
                    <Icon name="chevronRight" size={16} className="text-muted-2" />
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
        {lines.length > PEOPLE_SHOWN && (
          <div className="border-t border-line-subtle px-5 py-3">
            <CardLink to="/people" onOpen={onOpen}>
              See all {lines.length} {labels.person_plural.toLowerCase()}
            </CardLink>
          </div>
        )}
      </section>
    </div>
  );
}
