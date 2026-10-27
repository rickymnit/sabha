// /rubrics and /rubrics/:id (P6.8; docs/design/05-rubric-editor.png, read-only): how each conversation type is scored.
// Everyone signed in may read them, staff included, so they can see how they are judged (owner's decision,
// 2026-10-27). Editing and publishing wait for the calibration sample test (P5.9), and the design's "Agreement with
// raters" column waits for real rater scores (golden rule 6), so neither is shown.

import { useState, type MouseEvent } from "react";
import { Navigate, useNavigate, useOutletContext, useParams } from "react-router-dom";

import { useRubric, useRubrics } from "../api/hooks";
import type { Me, RubricDetail, RubricListItem } from "../api/types";
import { TYPE_INFO } from "../app/conversationTypes";
import { capitalise } from "../app/format";
import { Button, EmptyState, Icon, PageHeader, Panel, Skeleton, SkeletonGroup, Table, TypeDot, cx } from "../design";

type Dimension = RubricDetail["dimensions"][number];
type Change = RubricDetail["changes"][number];

const percent = (weight: number) => `${Math.round(weight * 100)}%`;

/** A link that changes page without reloading (keeps cmd/ctrl-click for a new tab). */
function useOpen() {
  const navigate = useNavigate();
  return (event: MouseEvent<HTMLAnchorElement>, to: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(to);
  };
}

export function RubricsPage() {
  const { id } = useParams();
  const me = useOutletContext<Me>();
  const list = useRubrics();
  const things = me.tenant.labels.recording_plural.toLowerCase();

  if (list.isError) {
    return (
      <Panel>
        <EmptyState
          icon={<Icon name="alert" size={26} />}
          title="We couldn't load the rubrics"
          description="Please try again in a moment."
          action={<Button onClick={() => void list.refetch()}>Try again</Button>}
        />
      </Panel>
    );
  }
  if (list.isPending) {
    return (
      <SkeletonGroup label="Loading rubrics" className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </SkeletonGroup>
    );
  }
  const items = list.data.items;
  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Rubrics" />
        <Panel>
          <EmptyState
            className="py-14"
            icon={<Icon name="rubrics" size={26} />}
            title="No rubrics yet"
            description="Rubrics appear here once a conversation type is set up for your organisation."
          />
        </Panel>
      </div>
    );
  }
  const selected = id ?? items[0]?.current_id;
  if (!id && selected) return <Navigate to={`/rubrics/${encodeURIComponent(selected)}`} replace />;

  return (
    <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
      <RubricNav items={items} selected={selected} />
      <div className="min-w-0">{selected && <RubricView id={selected} things={things} />}</div>
    </div>
  );
}

function RubricNav({ items, selected }: { items: RubricListItem[]; selected: string | undefined }) {
  const open = useOpen();
  return (
    <nav aria-label="All rubrics" className="flex flex-col gap-1">
      <p className="m-0 px-2.5 pb-1.5 text-caption font-semibold text-muted-2">All rubrics</p>
      {items.map((item) => {
        const current = item.versions.some((v) => v.id === selected);
        const href = `/rubrics/${encodeURIComponent(item.current_id)}`;
        return (
          <a
            key={item.type}
            href={href}
            onClick={(e) => open(e, href)}
            aria-current={current ? "page" : undefined}
            className={cx(
              "flex min-h-touch items-center justify-between gap-2 rounded px-2.5 py-1.5 no-underline",
              current ? "bg-primary-tint text-primary-hover" : "text-ink-2 hover:bg-surface-subtle",
            )}
          >
            <span className="flex min-w-0 flex-col">
              <TypeDot type={item.type} label={<span className="font-semibold">{TYPE_INFO[item.type].name}</span>} />
              <span className="pl-3.5 text-caption text-muted-2">
                v{item.versions.find((v) => v.in_use)?.version}, {item.dimension_count} dimensions
              </span>
            </span>
          </a>
        );
      })}
    </nav>
  );
}

function RubricView({ id, things }: { id: string; things: string }) {
  const rubric = useRubric(id);
  if (rubric.isError) {
    return (
      <Panel>
        <EmptyState
          icon={<Icon name={rubric.error.status === 404 ? "rubrics" : "alert"} size={26} />}
          title={
            rubric.error.status === 404
              ? "This rubric is not used by your organisation"
              : "We couldn't load this rubric"
          }
          description={rubric.error.status === 404 ? "Choose one from the list." : "Please try again in a moment."}
          action={
            rubric.error.status === 404 ? undefined : <Button onClick={() => void rubric.refetch()}>Try again</Button>
          }
        />
      </Panel>
    );
  }
  if (rubric.isPending) {
    return (
      <SkeletonGroup label="Loading the rubric" className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </SkeletonGroup>
    );
  }
  if (!Array.isArray(rubric.data.dimensions) || !Array.isArray(rubric.data.versions)) {
    // An answer of an unexpected shape is shown as an error, never as a broken page.
    return (
      <Panel>
        <EmptyState icon={<Icon name="alert" size={26} />} title="We couldn't load this rubric" />
      </Panel>
    );
  }
  return <RubricBody key={rubric.data.id} rubric={rubric.data} things={things} />;
}

function RubricBody({ rubric, things }: { rubric: RubricDetail; things: string }) {
  const [chosen, setChosen] = useState(rubric.dimensions[0]?.key);
  const dimension = rubric.dimensions.find((d) => d.key === chosen) ?? rubric.dimensions[0];
  const name = TYPE_INFO[rubric.type].name;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={`${name} rubric`}
        description={
          rubric.in_use
            ? `Version ${rubric.version}, in use. Every ${name.toLowerCase()} recording is scored with it.`
            : `Version ${rubric.version}, an earlier version. ${capitalise(things)} scored with it keep their scores.`
        }
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-6">
          <Panel
            flush
            title="Dimensions"
            description="Each is scored 1 to 5 from what was said, and every score cites quotes from the transcript. Weights add up to 100%."
          >
            <Table<Dimension>
              aria-label="Dimensions"
              rows={rubric.dimensions}
              rowKey={(d) => d.key}
              minWidth={0}
              rowClassName="relative hover:bg-surface-faint"
              columns={[
                {
                  key: "name",
                  header: "Dimension",
                  render: (d) => (
                    <button
                      type="button"
                      onClick={() => setChosen(d.key)}
                      aria-pressed={d.key === dimension?.key}
                      className={cx(
                        "min-h-touch bg-transparent p-0 text-left after:absolute after:inset-0 after:content-['']",
                        d.key === dimension?.key ? "font-semibold text-primary-hover" : "text-ink",
                      )}
                    >
                      {d.name}
                    </button>
                  ),
                },
                { key: "weight", header: "Weight", align: "right", render: (d) => percent(d.weight) },
                { key: "quotes", header: "Quotes required", align: "right", render: (d) => d.min_quotes },
              ]}
            />
          </Panel>
          {dimension && <DimensionPanel dimension={dimension} />}
        </div>
        <aside className="flex flex-col gap-6">
          <VersionHistory rubric={rubric} />
        </aside>
      </div>
    </div>
  );
}

function DimensionPanel({ dimension }: { dimension: Dimension }) {
  return (
    <Panel title={dimension.name} headingAs="h2">
      <div className="flex flex-col gap-5">
        <dl className="m-0 grid grid-cols-2 gap-4 sm:max-w-md">
          <div>
            <dt className="text-small text-muted">Weight</dt>
            <dd className="m-0 font-semibold">{percent(dimension.weight)}</dd>
          </div>
          <div>
            <dt className="text-small text-muted">Quotes required per score</dt>
            <dd className="m-0 font-semibold">{dimension.min_quotes}</dd>
          </div>
        </dl>
        <section>
          <h3 className="m-0 mb-1.5 text-sm font-semibold">What this measures</h3>
          <p className="m-0 text-ink-2">{dimension.definition}</p>
        </section>
        {dimension.not_applicable_when && (
          <section>
            <h3 className="m-0 mb-1.5 text-sm font-semibold">Not scored when</h3>
            <p className="m-0 text-ink-2">{dimension.not_applicable_when}</p>
          </section>
        )}
        <section>
          <h3 className="m-0 mb-2 text-sm font-semibold">Scale, with examples</h3>
          <ol className="m-0 flex list-none flex-col gap-2 p-0">
            {dimension.scale.map((level) => (
              <li key={level.level} className="flex gap-3 rounded border border-line px-3.5 py-3">
                <span
                  aria-label={`Level ${level.level}`}
                  className={cx(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded text-caption font-semibold",
                    level.level < 3
                      ? "bg-danger-tint text-danger"
                      : level.level < 4
                        ? "bg-warning-tint text-warning-ink"
                        : "bg-success-tint text-success",
                  )}
                >
                  {level.level}
                </span>
                <span className="flex min-w-0 flex-col gap-1">
                  <span>{level.description}</span>
                  {level.example && (
                    <span className="text-small text-muted">
                      Example: <q className="italic">{level.example}</q>
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </Panel>
  );
}

const ITEM_NAMES: Record<string, string> = {
  name: "Name",
  weight: "Weight",
  definition: "What it measures",
  min_quotes: "Quotes required",
  not_applicable_when: "When it is not scored",
  "dimension added": "Added",
  "dimension removed": "Removed",
  "dimension order": "Order of dimensions",
};

/** "Checks for understanding: level 2 description", in plain words. */
function describe(change: Change, names: Map<string, string>): string {
  const where = change.dimension ? (names.get(change.dimension) ?? change.dimension.replaceAll("_", " ")) : "Rubric";
  const level = /^(anchors|examples)\[(\d)\]$/.exec(change.item);
  let what = ITEM_NAMES[change.item] ?? change.item.replaceAll("_", " ");
  if (level) what = `level ${level[2]} ${level[1] === "anchors" ? "description" : "example"}`;
  if (change.item === "weight" && change.old && change.new) {
    what = `weight ${percent(Number(change.old))} to ${percent(Number(change.new))}`;
  } else if (change.item === "min_quotes" && change.old && change.new) {
    what = `quotes required ${change.old} to ${change.new}`;
  }
  return `${capitalise(where)}: ${what.charAt(0).toLowerCase()}${what.slice(1)}`;
}

const SHOWN_CHANGES = 8;

function VersionHistory({ rubric }: { rubric: RubricDetail }) {
  const open = useOpen();
  const [all, setAll] = useState(false);
  const names = new Map(rubric.dimensions.map((d) => [d.key, d.name]));
  const changes = all ? rubric.changes : rubric.changes.slice(0, SHOWN_CHANGES);
  const previous = rubric.versions.find((v) => v.id === rubric.previous_id);
  return (
    <>
      <Panel title="Version history" headingAs="h2">
        <ol className="m-0 flex list-none flex-col gap-1 p-0">
          {rubric.versions.map((v) => {
            const href = `/rubrics/${encodeURIComponent(v.id)}`;
            const here = v.id === rubric.id;
            return (
              <li key={v.id}>
                <a
                  href={href}
                  onClick={(e) => open(e, href)}
                  aria-current={here ? "page" : undefined}
                  className={cx(
                    "flex min-h-touch items-center gap-2.5 rounded px-2 no-underline",
                    here ? "bg-surface-subtle font-semibold text-ink" : "text-ink-2 hover:bg-surface-subtle",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cx(
                      "h-3 w-3 shrink-0 rounded-full border-2",
                      v.in_use ? "border-primary bg-primary" : "border-line-input",
                    )}
                  />
                  <span>v{v.version}</span>
                  {v.in_use && <span className="text-caption font-semibold text-success">In use</span>}
                </a>
              </li>
            );
          })}
        </ol>
      </Panel>
      {previous && (
        <Panel title={`Changes from v${previous.version}`} headingAs="h2">
          {rubric.changes.length === 0 ? (
            <p className="m-0 text-muted">The content is the same.</p>
          ) : (
            <>
              <ul className="m-0 flex flex-col gap-1.5 pl-4 text-sm">
                {changes.map((c, i) => (
                  <li key={`${c.dimension}-${c.item}-${i}`}>{describe(c, names)}</li>
                ))}
              </ul>
              {rubric.changes.length > SHOWN_CHANGES && (
                <Button variant="ghost" className="mt-2" onClick={() => setAll((v) => !v)}>
                  {all ? "Show fewer" : `Show all ${rubric.changes.length} changes`}
                </Button>
              )}
            </>
          )}
        </Panel>
      )}
    </>
  );
}
