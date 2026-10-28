// /people: the people the signed-in person may see (all for owners and admins, their units for managers and
// reviewers), each with how many recordings are analysed, the latest overall score and the recent trend. Every
// number is a real count or score from GET /v1/people/summary (golden rule 6). A row opens that person's
// recordings. Staff have no People page (app/nav.ts); they see only themselves anyway.

import { useState, type MouseEvent } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { usePeopleSummary } from "../api/hooks";
import type { Me, PersonSummary } from "../api/types";
import {
  Avatar,
  Button,
  EmptyState,
  Icon,
  Input,
  PageHeader,
  Panel,
  ScoreChip,
  Skeleton,
  SkeletonGroup,
  Sparkline,
  Table,
} from "../design";
import { capitalise, formatWhen } from "../app/format";
import { unitLabel } from "../app/units";
import { PersonDialog } from "../features/organisation/PersonDialog";
import { formatScore } from "../features/report/format";

function trendLabel(person: PersonSummary, things: string): string {
  const scores = person.recent_scores;
  if (scores.length === 0) return "No scores yet";
  const low = formatScore(Math.min(...scores));
  const high = formatScore(Math.max(...scores));
  const latest = formatScore(scores.at(-1) as number);
  return `Last ${scores.length} ${things}: ${low} to ${high}, latest ${latest}`;
}

export function PeoplePage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const navigate = useNavigate();
  const people = usePeopleSummary();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<PersonSummary | "new" | null>(null);
  const isAdmin = me.user.role === "owner" || me.user.role === "admin"; // who adds and edits people (owner, 2026-10-28)
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));
  // "Class 6 · A, Class 7 · B": every unit the person works in, home first
  const where = (p: PersonSummary) =>
    (p.unit_ids?.length ? p.unit_ids : p.unit_id ? [p.unit_id] : [])
      .map((id) => unitLabel(me.tenant.units, id))
      .filter(Boolean)
      .join(", ");
  const plural = labels.person_plural.toLowerCase();
  const things = labels.recording_plural.toLowerCase();

  const needle = query.trim().toLowerCase();
  const rows = (people.data ?? []).filter(
    (p) => !needle || p.name.toLowerCase().includes(needle) || where(p).toLowerCase().includes(needle),
  );
  const open = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(`/recordings?person=${encodeURIComponent(id)}`);
  };

  const mine = me.user.unit_ids.map((id) => units.get(id)).filter(Boolean);
  const description =
    (me.user.role === "manager" || me.user.role === "reviewer") && mine.length
      ? `${capitalise(plural)} in ${mine.join(", ")}, with their latest scores.`
      : `Everyone in ${me.tenant.name} whose ${things} Sabha analyses.`;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={capitalise(labels.person_plural)}
        description={description}
        actions={
          isAdmin && (
            <Button icon={<Icon name="people" size={16} />} onClick={() => setEditing("new")}>
              Add {labels.person.toLowerCase()}
            </Button>
          )
        }
      />
      {editing && (
        <PersonDialog me={me} person={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />
      )}
      {people.isError ? (
        <Panel>
          <EmptyState
            icon={<Icon name="alert" size={26} />}
            title={`We couldn't load the ${plural}`}
            description="Please try again in a moment."
            action={<Button onClick={() => void people.refetch()}>Try again</Button>}
          />
        </Panel>
      ) : people.isSuccess && people.data.length === 0 ? (
        <Panel>
          <EmptyState
            className="py-14"
            icon={<Icon name="people" size={26} />}
            title={`No ${plural} yet`}
            description={`${capitalise(plural)} appear here once an administrator adds them.`}
          />
        </Panel>
      ) : (
        <Panel
          flush
          aria-label={capitalise(labels.person_plural)}
          actions={
            <Input
              label={`Search ${plural}`}
              hideLabel
              type="search"
              placeholder="Search by name"
              leadingIcon={<Icon name="search" size={16} />}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full sm:w-80"
            />
          }
          footer={
            people.isSuccess && (
              <span>
                {rows.length} {rows.length === 1 ? labels.person.toLowerCase() : plural}
              </span>
            )
          }
        >
          {people.isPending ? (
            <SkeletonGroup label={`Loading ${plural}`} className="flex flex-col gap-4 px-5 py-5">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3">
                  <Skeleton className="h-8 w-8 rounded-full" />
                  <Skeleton className="h-4 w-48" />
                </div>
              ))}
            </SkeletonGroup>
          ) : (
            <Table<PersonSummary>
              aria-label={capitalise(labels.person_plural)}
              rows={rows}
              rowKey={(p) => p.id}
              minWidth={0}
              rowClassName="relative hover:bg-surface-faint"
              empty={
                <EmptyState
                  headingAs="h3"
                  title={`No ${plural} match`}
                  action={
                    <Button variant="secondary" onClick={() => setQuery("")}>
                      Clear search
                    </Button>
                  }
                />
              }
              columns={[
                {
                  key: "name",
                  header: capitalise(labels.person),
                  render: (p) => (
                    <div className="flex items-center gap-3">
                      <Avatar name={p.name} />
                      <div className="flex min-w-0 flex-col">
                        <a
                          href={`/recordings?person=${encodeURIComponent(p.id)}`}
                          onClick={(e) => open(e, p.id)}
                          className="font-semibold text-ink no-underline after:absolute after:inset-0 hover:text-primary-hover"
                        >
                          {p.name}
                        </a>
                        <span className="text-small text-muted">{where(p)}</span>
                      </div>
                    </div>
                  ),
                },
                {
                  key: "analysed",
                  header: `${capitalise(things)} analysed`,
                  align: "right",
                  hideOnPhone: true,
                  render: (p) => p.analysed,
                },
                {
                  key: "trend",
                  header: "Recent trend",
                  hideOnPhone: true,
                  render: (p) =>
                    p.recent_scores.length ? (
                      <Sparkline scores={p.recent_scores} label={trendLabel(p, things)} />
                    ) : (
                      <span className="text-small text-muted-2">No scores yet</span>
                    ),
                },
                {
                  key: "latest",
                  header: "Latest score",
                  align: "right",
                  render: (p) => <ScoreChip score={p.latest_score} variant="text" decimals={1} />,
                },
                {
                  key: "when",
                  header: "Last analysed",
                  align: "right",
                  hideOnPhone: true,
                  className: "whitespace-nowrap",
                  render: (p) => (p.last_analysed_at ? formatWhen(p.last_analysed_at) : "—"),
                },
                ...(isAdmin
                  ? [
                      {
                        key: "edit",
                        header: <span className="sr-only">Edit</span>,
                        align: "right" as const,
                        render: (p: PersonSummary) => (
                          // above the row's link, which covers the whole row
                          <Button variant="ghost" className="relative z-10" onClick={() => setEditing(p)}>
                            Edit<span className="sr-only"> {p.name}</span>
                          </Button>
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          )}
        </Panel>
      )}
    </div>
  );
}
