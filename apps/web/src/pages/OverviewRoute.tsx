// /overview (docs/design/01-overview.png) for owners, admins, managers and reviewers: the period's numbers and
// "Where coaching helps most" (features/overview), what is being processed right now, and the newest recordings.
// Everything comes from the API for the recordings the signed-in person may see.

import { useState, type MouseEvent } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { useOverview, useRecordings } from "../api/hooks";
import type { Me, RecordingItem } from "../api/types";
import { capitalise, formatWhen, statusChip } from "../app/format";
import {
  Button,
  Card,
  EmptyState,
  Icon,
  Panel,
  ScoreChip,
  StatusChip,
  Table,
  cx,
  type CardTone,
  type ConversationType,
} from "../design";
import { OverviewPage } from "../features/overview/OverviewPage";
import { presetRange, toQuery, type DayRange, type RangePreset } from "../features/overview/range";
import type { StageCount } from "../features/overview/types";

const STAGE_CARDS: { title: string; note: string; stages: StageCount["stage"][]; warn?: boolean }[] = [
  { title: "Uploading", note: "Going straight to storage", stages: ["uploading", "queued"] },
  { title: "Preparing audio", note: "Removing silence, finding speakers", stages: ["preparing", "finding_speakers"] },
  { title: "Transcribing", note: "Speech to text", stages: ["transcribing"] },
  { title: "Scoring", note: "Rubric scores with quotes", stages: ["analysing"] },
  { title: "Needs review", note: "Unclear audio or speakers", stages: ["needs_review"], warn: true },
];

function Processing({ counts, onReview }: { counts: StageCount[]; onReview: () => void }) {
  const total = (stages: StageCount["stage"][]) =>
    counts.filter((c) => stages.includes(c.stage)).reduce((sum, c) => sum + c.n, 0);
  return (
    <Panel title="Processing now">
      <ul className="m-0 grid list-none grid-cols-2 gap-2.5 p-0 md:grid-cols-3 xl:grid-cols-5">
        {STAGE_CARDS.map((card) => {
          const n = total(card.stages);
          const tone: CardTone = n === 0 ? "neutral" : card.warn ? "warning" : "active";
          const body = (
            <>
              <span className="flex items-baseline justify-between gap-2">
                <span className="text-sm text-ink">{card.title}</span>
                <span className={cx("text-xl font-bold", n === 0 ? "text-muted-2" : "text-ink")}>{n}</span>
              </span>
              <span className="text-caption text-muted">{card.note}</span>
            </>
          );
          return (
            <Card as="li" key={card.title} tone={tone} className="min-h-[76px]">
              {card.warn && n > 0 ? (
                <button type="button" onClick={onReview} className="flex flex-col gap-2 text-left">
                  {body}
                </button>
              ) : (
                body
              )}
            </Card>
          );
        })}
      </ul>
    </Panel>
  );
}

function Recent({ me }: { me: Me }) {
  const navigate = useNavigate();
  const labels = me.tenant.labels;
  const recordings = useRecordings({}, 6);
  const rows = recordings.data?.pages[0]?.items ?? [];
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));
  const things = labels.recording_plural.toLowerCase();
  const open = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(`/recordings/${id}`);
  };
  return (
    <Panel
      flush
      title={`Recent ${things}`}
      footer={
        rows.length > 0 && (
          <a
            href="/recordings"
            onClick={(e) => {
              e.preventDefault();
              navigate("/recordings");
            }}
          >
            View all {things}
          </a>
        )
      }
    >
      {recordings.isSuccess && rows.length === 0 ? (
        <EmptyState
          headingAs="h3"
          title={`No ${things} yet`}
          action={<Button onClick={() => navigate("/upload")}>Upload</Button>}
        />
      ) : (
        <Table<RecordingItem>
          aria-label={`Recent ${things}`}
          rows={rows}
          rowKey={(r) => r.id}
          minWidth={0}
          rowClassName="relative hover:bg-surface-faint"
          columns={[
            {
              key: "title",
              header: capitalise(labels.recording),
              render: (r) => (
                <div className="flex flex-col gap-0.5">
                  <a
                    href={`/recordings/${r.id}`}
                    onClick={(e) => open(e, r.id)}
                    className="font-semibold text-ink no-underline after:absolute after:inset-0 hover:text-primary-hover"
                  >
                    {r.title}
                  </a>
                  <span className="text-small text-muted">
                    {[r.person?.name, r.unit_id ? units.get(r.unit_id) : undefined].filter(Boolean).join(", ")}
                  </span>
                </div>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (r) => {
                const { chip, text } = statusChip(r.status);
                return <StatusChip status={chip}>{text}</StatusChip>;
              },
            },
            {
              key: "score",
              header: "Score",
              align: "right",
              render: (r) => <ScoreChip score={r.overall_score} variant="text" decimals={1} />,
            },
            {
              key: "when",
              header: "Uploaded",
              align: "right",
              hideOnPhone: true,
              className: "whitespace-nowrap",
              render: (r) => formatWhen(r.created_at),
            },
          ]}
        />
      )}
    </Panel>
  );
}

export function OverviewRoute() {
  const me = useOutletContext<Me>();
  const navigate = useNavigate();
  const [preset, setPreset] = useState<RangePreset>("30d");
  const [range, setRange] = useState<DayRange>(() => presetRange("30d", new Date()));
  const overview = useOverview(toQuery(range));
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));
  const mine = me.user.unit_ids.map((id) => units.get(id)).filter(Boolean);
  const scopeLabel = mine.length ? mine.join(", ") : me.tenant.name;
  const typeNames = Object.fromEntries(
    (["teaching", "reception", "counselling", "meeting", "sales"] as ConversationType[]).map((t) => [t, capitalise(t)]),
  ) as Record<ConversationType, string>;

  if (overview.isError) {
    return (
      <Panel>
        <EmptyState
          icon={<Icon name="alert" size={26} />}
          title="We couldn't load the overview"
          description="Please try again in a moment."
          action={<Button onClick={() => void overview.refetch()}>Try again</Button>}
        />
      </Panel>
    );
  }
  return (
    <OverviewPage
      stats={overview.data}
      scopeLabel={scopeLabel}
      preset={preset}
      range={range}
      onRangeChange={(p, r) => {
        setPreset(p);
        setRange(r);
      }}
      typeNames={typeNames}
      labels={me.tenant.labels}
      processing={
        overview.data && (
          <Processing counts={overview.data.in_progress ?? []} onReview={() => navigate("/recordings")} />
        )
      }
      recent={<Recent me={me} />}
    />
  );
}
