// /activity (P1.8): the audit log for owners and admins, in plain words. Who played which recording's audio, opened
// which report, disputed or decided a score, changed settings or invited someone, newest first. Entries can never
// be changed (the API refuses), so this page only reads. Filters: what was done, who did it, and when.

import { useState, type MouseEvent } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAudit } from "../api/hooks";
import type { AuditEntryItem, Me } from "../api/types";
import { capitalise, formatDateTime, formatWhen } from "../app/format";
import { Button, EmptyState, Icon, PageHeader, Panel, Select, Skeleton, SkeletonGroup, Table } from "../design";
import { actionChoices, describe, roleWord } from "../features/activity/describe";

const PERIODS = [
  { value: "1", label: "Today and yesterday" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "", label: "All time" },
];

function since(days: string, now: Date = new Date()): string | null {
  return days ? new Date(now.getTime() - Number(days) * 86_400_000).toISOString() : null;
}

export function ActivityPage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const navigate = useNavigate();
  const [action, setAction] = useState("");
  const [period, setPeriod] = useState("30");
  const [actor, setActor] = useState<{ id: string; name: string } | null>(null);
  const [from] = useState(() => new Map<string, string | null>());
  // One start time per period choice, so the query key stays stable while the page is open.
  if (!from.has(period)) from.set(period, since(period));
  const audit = useAudit({ action: action || null, actorUserId: actor?.id ?? null, from: from.get(period) ?? null });
  const rows = audit.data?.pages.flatMap((page) => page.items) ?? [];
  const filtered = Boolean(action || actor || period !== "30");

  const open = (event: MouseEvent<HTMLAnchorElement>, href: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(href);
  };
  const clear = () => {
    setAction("");
    setActor(null);
    setPeriod("30");
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Activity"
        description={`Who listened to, opened or changed what in ${me.tenant.name}. Entries are kept as they were written and cannot be edited.`}
      />
      <Panel
        flush
        aria-label="Activity"
        actions={
          <div className="flex flex-wrap items-end gap-3">
            <Select label="What" value={action} onChange={(e) => setAction(e.target.value)} className="w-56">
              <option value="">Everything</option>
              {actionChoices(labels).map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </Select>
            <Select label="When" value={period} onChange={(e) => setPeriod(e.target.value)} className="w-48">
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </Select>
            {actor && (
              <Button
                variant="secondary"
                onClick={() => setActor(null)}
                aria-label={`Show everyone, not only ${actor.name}`}
              >
                Only {actor.name}
                <Icon name="close" size={16} />
              </Button>
            )}
          </div>
        }
        footer={
          audit.isSuccess &&
          rows.length > 0 && (
            <div className="flex items-center justify-between gap-3">
              <span>
                {rows.length} {rows.length === 1 ? "entry" : "entries"}
                {audit.hasNextPage ? " so far" : ""}
              </span>
              {audit.hasNextPage && (
                <Button
                  variant="secondary"
                  onClick={() => void audit.fetchNextPage()}
                  disabled={audit.isFetchingNextPage}
                >
                  {audit.isFetchingNextPage ? "Loading…" : "Show older"}
                </Button>
              )}
            </div>
          )
        }
      >
        {audit.isError ? (
          <EmptyState
            headingAs="h3"
            icon={<Icon name="alert" size={26} />}
            title="We couldn't load the activity"
            description={`Please try again in a moment.${audit.error instanceof ApiError && audit.error.requestId ? ` If it keeps happening, quote reference ${audit.error.requestId}.` : ""}`}
            action={<Button onClick={() => void audit.refetch()}>Try again</Button>}
          />
        ) : audit.isPending ? (
          <SkeletonGroup label="Loading activity" className="flex flex-col gap-4 px-5 py-5">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-4 w-full max-w-xl" />
            ))}
          </SkeletonGroup>
        ) : (
          <Table<AuditEntryItem>
            aria-label="Activity"
            rows={rows}
            rowKey={(entry) => entry.id}
            minWidth={0}
            empty={
              <EmptyState
                headingAs="h3"
                className="py-12"
                icon={<Icon name="clock" size={26} />}
                title={filtered ? "Nothing matches these filters" : "No activity yet"}
                description={
                  filtered
                    ? undefined
                    : `Playing audio, opening reports, disputes, settings changes and invites appear here.`
                }
                action={
                  filtered ? (
                    <Button variant="secondary" onClick={clear}>
                      Clear filters
                    </Button>
                  ) : undefined
                }
              />
            }
            columns={[
              {
                key: "when",
                header: "When",
                className: "whitespace-nowrap text-muted",
                render: (entry) => (
                  <time dateTime={entry.at} title={formatDateTime(entry.at)}>
                    {formatWhen(entry.at)}
                  </time>
                ),
              },
              {
                key: "who",
                header: "Who",
                render: (entry) =>
                  entry.actor.name ? (
                    <button
                      type="button"
                      onClick={() => setActor({ id: entry.actor.id, name: entry.actor.name ?? "" })}
                      title={`Show only ${entry.actor.name}`}
                      className="flex min-h-touch flex-col items-start bg-transparent p-0 text-left"
                    >
                      <span className="font-semibold text-ink">{entry.actor.name}</span>
                      <span className="text-caption text-muted-2">{roleWord(entry.actor.role, labels)}</span>
                    </button>
                  ) : (
                    <span className="text-muted">Someone no longer here</span>
                  ),
              },
              {
                key: "what",
                header: "What",
                render: (entry) => {
                  const d = describe(entry, labels);
                  return (
                    <span>
                      {capitalise(d.text)}
                      {d.target && " "}
                      {d.target &&
                        (d.href ? (
                          <a href={d.href} onClick={(e) => open(e, d.href as string)}>
                            {d.target}
                          </a>
                        ) : (
                          <span className="font-semibold">{d.target}</span>
                        ))}
                      {d.after}
                    </span>
                  );
                },
              },
            ]}
          />
        )}
      </Panel>
    </div>
  );
}
