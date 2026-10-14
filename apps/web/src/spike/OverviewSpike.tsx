// Week 0 design spike (P0.2): reproduces docs/design/01-overview.png with static data.
// Throwaway code. P6.1 builds the real components in src/design/; P1.7 brings the real label dictionary.

import { useState, type ReactNode } from "react";

// Stand-in for the tenant's `labels` dictionary: UI nouns are looked up here, never hard-coded.
const labels = {
  recordings: "recordings",
  people: "people",
  units: "campuses",
  allUnits: "All campuses",
};

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

type TypeKey = "teaching" | "reception" | "counselling" | "meeting" | "sales";
type Status = "Analysed" | "Transcribing" | "Analysing" | "Needs review";
type Tone = "neutral" | "active" | "warning";

const conversationTypes: { key: TypeKey; label: string; singular: string; count: number }[] = [
  { key: "teaching", label: "Teaching", singular: "Teaching", count: 128 },
  { key: "reception", label: "Reception", singular: "Reception", count: 46 },
  { key: "counselling", label: "Counselling", singular: "Counselling", count: 17 },
  { key: "meeting", label: "Meetings", singular: "Meeting", count: 12 },
  { key: "sales", label: "Sales", singular: "Sales", count: 11 },
];

// Full class names so Tailwind can see them.
const typeSwatch: Record<TypeKey, string> = {
  teaching: "bg-type-teaching",
  reception: "bg-type-reception",
  counselling: "bg-type-counselling",
  meeting: "bg-type-meeting",
  sales: "bg-type-sales",
};

const statusChip: Record<Status, string> = {
  Analysed: "bg-success-tint text-success",
  Transcribing: "bg-primary-tint text-primary-hover",
  Analysing: "bg-primary-tint text-primary-hover",
  "Needs review": "bg-warning-tint text-warning-ink",
};

const stageTone: Record<Tone, { card: string; count: string }> = {
  neutral: { card: "bg-surface-subtle border-line-subtle", count: "text-ink" },
  active: { card: "bg-primary-tint-subtle border-primary-tint-strong", count: "text-primary-hover" },
  warning: { card: "bg-warning-surface border-warning-border", count: "text-warning-ink" },
};

// Overview bands (Main.dc.html:233-239). The report page uses different bands; see tokens.md.
function scoreTone(score: number | null): string {
  if (score === null) return "text-muted-2";
  if (score < 3) return "text-danger";
  if (score < 3.5) return "text-warning";
  return "text-success";
}

const metrics: { label: string; value: ReactNode; foot: ReactNode }[] = [
  {
    label: `${capitalise(labels.recordings)} analysed`,
    value: "214",
    foot: <span className="text-success">32 more than last week</span>,
  },
  { label: "Audio processed", value: "162 h", foot: <span className="text-muted">41 h of silence removed</span> },
  {
    label: "Median teaching score",
    value: (
      <>
        3.5<span className="text-lg font-medium text-muted-2"> / 5</span>
      </>
    ),
    foot: <span className="text-success">Up 0.2 since September</span>,
  },
  { label: "Scores disputed by staff", value: "7", foot: <a href="#">Review disputes</a> },
];

const stages: { name: string; count: number; note: string; tone: Tone }[] = [
  { name: "Uploading", count: 3, note: "Resumable, direct to storage", tone: "neutral" },
  { name: "Cleaning audio", count: 2, note: "Silence removal, diarization", tone: "neutral" },
  { name: "Transcribing", count: 5, note: "Hindi, English, Hinglish", tone: "active" },
  { name: "Scoring", count: 4, note: "Rubric scoring with evidence", tone: "active" },
  { name: "Needs review", count: 2, note: "Low audio quality, unclear roles", tone: "warning" },
];

const recordings: {
  title: string;
  person: string;
  type: TypeKey;
  length: string;
  status: Status;
  score: number | null;
  uploaded: string;
}[] = [
  {
    title: "Class 8 Science: Photosynthesis",
    person: "Anjali Sharma, Main campus",
    type: "teaching",
    length: "52:14",
    status: "Analysed",
    score: 3.0,
    uploaded: "Today, 11:20",
  },
  {
    title: "Admission enquiry for Grade 3",
    person: "Front desk, Main campus",
    type: "reception",
    length: "06:48",
    status: "Analysed",
    score: 4.2,
    uploaded: "Today, 10:05",
  },
  {
    title: "Class 10 Maths: Quadratic equations",
    person: "Rohit Meena, Vaishali Nagar",
    type: "teaching",
    length: "47:02",
    status: "Transcribing",
    score: null,
    uploaded: "Today, 09:40",
  },
  {
    title: "Fee concession follow-up",
    person: "Front desk, Mansarovar",
    type: "reception",
    length: "04:12",
    status: "Needs review",
    score: null,
    uploaded: "Today, 09:12",
  },
  {
    title: "Parent meeting about attendance",
    person: "Neha Joshi, Counsellor",
    type: "counselling",
    length: "28:30",
    status: "Analysed",
    score: 3.9,
    uploaded: "Yesterday",
  },
  {
    title: "Weekly academic council",
    person: "6 participants",
    type: "meeting",
    length: "41:55",
    status: "Analysing",
    score: null,
    uploaded: "Yesterday",
  },
  {
    title: "ERP demo for a partner school",
    person: "Karan Singh, Sales",
    type: "sales",
    length: "33:10",
    status: "Analysed",
    score: 2.8,
    uploaded: "10 Oct",
  },
];
const totalRecordings = 214;

const weakest: { name: string; score: number; note: string; tone: "danger" | "warning" }[] = [
  { name: "Checks for understanding", score: 2.6, note: "Teaching, 128 lessons", tone: "danger" },
  { name: "Objection handling", score: 2.7, note: "Sales, 11 calls", tone: "danger" },
  { name: "Recap and closure", score: 2.9, note: "Teaching, 128 lessons", tone: "danger" },
  { name: "Resolution confirmed", score: 3.2, note: "Reception, 46 calls", tone: "warning" },
];

function Icon({
  children,
  size = 18,
  stroke = 1.7,
  className,
}: {
  children: ReactNode;
  size?: number;
  stroke?: number;
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {children}
    </svg>
  );
}

const navItems: { label: string; icon: ReactNode; badge?: number; current?: boolean }[] = [
  {
    label: "Overview",
    current: true,
    icon: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
  },
  { label: capitalise(labels.recordings), icon: <path d="M3 12h1M7 8v8M11 5v14M15 9v6M19 11v2" /> },
  {
    label: "Reviews",
    badge: 7,
    icon: (
      <>
        <path d="M4 5h16v11H9l-5 4z" />
        <path d="M9 10.5l2 2 4-4" />
      </>
    ),
  },
  {
    label: capitalise(labels.people),
    icon: (
      <>
        <circle cx="9" cy="8" r="3.5" />
        <path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" />
        <path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c1.8.7 3 2.4 3.5 5.2" />
      </>
    ),
  },
  {
    label: "Rubrics",
    icon: (
      <>
        <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" />
        <circle cx="16" cy="6" r="2" />
        <circle cx="10" cy="12" r="2" />
        <circle cx="18" cy="18" r="2" />
      </>
    ),
  },
];

function Sidebar() {
  return (
    <nav
      aria-label="Main"
      className="flex max-w-full flex-[1_1_232px] flex-col gap-6 border-r border-line bg-surface px-3.5 py-5"
    >
      <div className="flex items-center gap-2.5 px-2">
        <div
          aria-hidden="true"
          className="flex h-[30px] w-[30px] items-center justify-center gap-0.5 rounded bg-primary"
        >
          <div className="h-2 w-[3px] rounded-xs bg-surface" />
          <div className="h-4 w-[3px] rounded-xs bg-surface" />
          <div className="h-[11px] w-[3px] rounded-xs bg-brand-accent" />
          <div className="h-1.5 w-[3px] rounded-xs bg-surface" />
        </div>
        <div className="text-brand font-bold">Sabha</div>
      </div>

      <button
        type="button"
        className="flex min-h-touch w-full items-center justify-between gap-2 rounded border border-line bg-surface-subtle px-2.5 py-2 text-left text-ink"
      >
        <span className="flex flex-col">
          <span className="text-sm font-semibold">Greenfield Public School</span>
          <span className="text-caption text-muted-2">3 {labels.units}</span>
        </span>
        <Icon size={16} stroke={1.8} className="text-muted-2">
          <path d="M7 10l5-5 5 5M7 14l5 5 5-5" />
        </Icon>
      </button>

      <div className="flex flex-col gap-0.5">
        {navItems.map((item) => (
          <a
            key={item.label}
            href="#"
            aria-current={item.current ? "page" : undefined}
            className={`flex min-h-10 items-center justify-between gap-2.5 rounded px-2.5 no-underline ${
              item.current ? "bg-primary-tint font-semibold text-primary-hover" : "text-ink-2"
            }`}
          >
            <span className="flex items-center gap-2.5">
              <Icon>{item.icon}</Icon>
              {item.label}
            </span>
            {item.badge !== undefined && (
              // 36px = the design's min-width 22px + 7px padding each side, which it renders content-box.
              <span className="min-w-[36px] rounded-full bg-warning-tint px-[7px] py-px text-center text-caption font-semibold text-warning-ink">
                {item.badge}
              </span>
            )}
          </a>
        ))}
      </div>

      <div className="flex flex-col gap-0.5">
        <div className="px-2.5 pb-1.5 text-caption font-semibold text-muted-2">Conversation types</div>
        {conversationTypes.map((t) => (
          <a
            key={t.key}
            href="#"
            className="flex min-h-9 items-center justify-between rounded px-2.5 text-ink-2 no-underline"
          >
            <span className="flex items-center gap-2.5">
              <span className={`h-2 w-2 rounded-xs ${typeSwatch[t.key]}`} />
              {t.label}
            </span>
            <span className="text-caption text-muted-2">{t.count}</span>
          </a>
        ))}
      </div>

      <a
        href="#"
        className="mt-auto flex flex-col gap-2 rounded-card border border-line-subtle p-3 text-ink no-underline"
      >
        <span className="flex justify-between gap-2 text-sm">
          <span className="font-semibold">Starter plan</span>
          <span className="font-semibold text-primary">Manage</span>
        </span>
        <span aria-hidden="true" className="block h-1.5 overflow-hidden rounded-full bg-track">
          <span className="block h-1.5 rounded-full bg-primary" style={{ width: "38.4%" }} />
        </span>
        <span className="text-caption text-muted">38 of 100 audio hours used</span>
      </a>

      <div className="flex items-center gap-2.5 border-t border-line-subtle p-2.5">
        <div
          aria-hidden="true"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-tint-strong text-sm font-bold text-primary-hover"
        >
          PK
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold">Priya Kapoor</span>
          <span className="text-caption text-muted-2">Academic head</span>
        </div>
      </div>
    </nav>
  );
}

function Header() {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-title font-bold">Overview</h1>
        <p className="text-muted">{labels.allUnits}, 6 to 12 October 2026</p>
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        {/* The design sets outline:none on the input, which hides focus; the ring moves to the label instead. */}
        <label className="flex min-h-touch items-center gap-2 rounded border border-line-input bg-surface px-3 text-muted-2 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary">
          <Icon size={16} stroke={1.8}>
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" />
          </Icon>
          <span className="sr-only">Search {labels.recordings}</span>
          <input
            type="search"
            placeholder={`Search ${labels.people}, topics, quotes`}
            className="w-[220px] max-w-[46vw] border-0 bg-transparent text-ink placeholder:text-muted-2 focus-visible:outline-none"
          />
        </label>
        <button
          type="button"
          className="flex min-h-touch items-center gap-2 rounded border border-line-input bg-surface px-3.5 text-ink"
        >
          <Icon size={16} stroke={1.8}>
            <rect x="3" y="5" width="18" height="16" rx="2" />
            <path d="M3 10h18M8 3v4M16 3v4" />
          </Icon>
          Last 7 days
        </button>
        <a
          href="#"
          className="flex min-h-touch items-center gap-2 rounded bg-primary px-4 font-semibold text-surface no-underline hover:bg-primary-hover"
        >
          <Icon size={16} stroke={2}>
            <path d="M12 16V4M7 9l5-5 5 5M4 16v4h16v-4" />
          </Icon>
          Upload {labels.recordings}
        </a>
      </div>
    </header>
  );
}

function MetricStrip() {
  return (
    <section
      aria-label="This week"
      className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] overflow-hidden rounded-panel border border-line bg-surface"
    >
      {metrics.map((m, i) => (
        <div
          key={m.label}
          className={`flex flex-col gap-1.5 px-5 py-4.5 ${i < metrics.length - 1 ? "border-r border-line-subtle" : ""}`}
        >
          <span className="text-sm text-muted">{m.label}</span>
          <span className="text-metric font-semibold">{m.value}</span>
          <span className="text-small">{m.foot}</span>
        </div>
      ))}
    </section>
  );
}

function ProcessingNow() {
  return (
    <section
      aria-labelledby="queue-h"
      className="flex flex-col gap-3.5 rounded-panel border border-line bg-surface px-5 py-4.5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="queue-h" className="text-lg font-semibold">
          Processing now
        </h2>
        <span className="text-sm text-muted">
          Median turnaround for a 60-minute lecture: <strong className="font-semibold text-ink">18 min</strong>
        </span>
      </div>
      <ol className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2">
        {stages.map((s) => (
          <li key={s.name} className={`flex flex-col gap-2 rounded-card border px-3.5 py-3 ${stageTone[s.tone].card}`}>
            <span className="flex items-baseline justify-between">
              <span className="text-sm text-ink-2">{s.name}</span>
              <span className={`text-2xl font-semibold ${stageTone[s.tone].count}`}>{s.count}</span>
            </span>
            <span className="text-caption text-muted">{s.note}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RecentRecordings() {
  const [filter, setFilter] = useState<TypeKey | "all">("all");
  const rows = filter === "all" ? recordings : recordings.filter((r) => r.type === filter);
  const filters: { key: TypeKey | "all"; label: string }[] = [{ key: "all", label: "All" }, ...conversationTypes];
  const singular = Object.fromEntries(conversationTypes.map((t) => [t.key, t.singular])) as Record<TypeKey, string>;
  const th = "border-b border-line-subtle py-2.5 text-left font-medium";

  return (
    <section
      aria-labelledby="rec-h"
      className="min-w-0 flex-[999_1_640px] overflow-hidden rounded-panel border border-line bg-surface"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-subtle px-5 py-4">
        <h2 id="rec-h" className="text-lg font-semibold">
          Recent {labels.recordings}
        </h2>
        <div
          role="group"
          aria-label="Filter by type"
          className="flex flex-wrap gap-1 rounded-seg-outer bg-fill p-[3px]"
        >
          {filters.map((f) => {
            const pressed = filter === f.key;
            return (
              <button
                key={f.key}
                type="button"
                aria-pressed={pressed}
                onClick={() => setFilter(f.key)}
                className={`min-h-8 rounded-seg px-3 text-sm ${pressed ? "bg-surface font-semibold text-ink shadow-seg" : "text-muted"}`}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-table">
          <thead>
            <tr className="text-small text-muted">
              <th scope="col" className={`${th} px-5`}>
                Recording
              </th>
              <th scope="col" className={`${th} px-3`}>
                Type
              </th>
              <th scope="col" className={`${th} px-3`}>
                Length
              </th>
              <th scope="col" className={`${th} px-3`}>
                Status
              </th>
              <th scope="col" className={`${th} px-3 text-right`}>
                Score
              </th>
              <th scope="col" className={`${th} pl-3 pr-5 text-right`}>
                Uploaded
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.title}>
                <td className="border-b border-track px-5 py-3">
                  <a href="#" className="block font-semibold text-ink no-underline">
                    {r.title}
                  </a>
                  <span className="text-small text-muted">{r.person}</span>
                </td>
                <td className="border-b border-track p-3">
                  <span className="inline-flex items-center gap-1.5 text-sm text-ink-2">
                    <span className={`h-2 w-2 rounded-xs ${typeSwatch[r.type]}`} />
                    {singular[r.type]}
                  </span>
                </td>
                <td className="border-b border-track p-3 text-ink-2">{r.length}</td>
                <td className="border-b border-track p-3">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-[9px] py-[3px] text-small font-semibold ${statusChip[r.status]}`}
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                    {r.status}
                  </span>
                </td>
                <td className={`border-b border-track p-3 text-right font-semibold ${scoreTone(r.score)}`}>
                  {r.score === null ? "—" : r.score.toFixed(1)}
                </td>
                <td className="border-b border-track py-3 pl-3 pr-5 text-right text-muted">{r.uploaded}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between px-5 py-3 text-sm text-muted">
        <span>
          Showing {rows.length} of {totalRecordings}
        </span>
        <a href="#">View all {labels.recordings}</a>
      </div>
    </section>
  );
}

// Basis 340px matches 01-overview.png; Main.dc.html:202 says 300px but the screenshot renders about 341px wide.
function CoachingFocus() {
  return (
    <aside
      aria-labelledby="weak-h"
      className="flex min-w-0 flex-[1_1_340px] flex-col gap-4 rounded-panel border border-line bg-surface px-5 py-4.5"
    >
      <div className="flex flex-col gap-1">
        <h2 id="weak-h" className="text-lg font-semibold">
          Where coaching helps most
        </h2>
        <p className="text-sm text-muted">Lowest median dimension scores this week</p>
      </div>
      {weakest.map((w) => (
        <div key={w.name} className="flex flex-col gap-1.5">
          <div className="flex justify-between gap-2 text-table font-semibold">
            <span>{w.name}</span>
            <span className={w.tone === "danger" ? "text-danger" : "text-warning"}>{w.score.toFixed(1)}</span>
          </div>
          <div aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-track">
            <div
              className={`h-1.5 rounded-full ${w.tone === "danger" ? "bg-danger" : "bg-warning"}`}
              style={{ width: `${(w.score / 5) * 100}%` }}
            />
          </div>
          <span className="text-small text-muted">{w.note}</span>
        </div>
      ))}
      <a href="#" className="text-sm font-semibold">
        Open teaching rubric
      </a>
    </aside>
  );
}

export default function OverviewSpike() {
  return (
    <div className="flex min-h-screen flex-wrap">
      <Sidebar />
      <main className="flex min-w-0 flex-[999_1_560px] flex-col gap-6 px-[clamp(16px,3vw,40px)] pb-12 pt-7">
        <Header />
        <MetricStrip />
        <ProcessingNow />
        <div className="flex flex-wrap items-start gap-6">
          <RecentRecordings />
          <CoachingFocus />
        </div>
      </main>
    </div>
  );
}
