// Story-like page for the design components, served at /dev/components in development only (see main.tsx).
// Static sample data. UI nouns come from the stand-in `labels` below, as they will from the tenant's dictionary.

import { useState, type ReactNode } from "react";

import {
  Button,
  Card,
  Checkbox,
  EmptyState,
  Input,
  MetricStrip,
  NavItem,
  PageHeader,
  Panel,
  ProgressBar,
  ScoreBar,
  ScoreChip,
  SegmentedControl,
  Select,
  Skeleton,
  SkeletonGroup,
  StatusChip,
  Table,
  Tabs,
  Toast,
  ToastProvider,
  TypeDot,
  useToast,
  type ConversationType,
  type Metric,
  type RecordingStatus,
  type TableColumn,
} from "../design";

// Stand-in for the tenant's labels dictionary (P1.7 brings the real one).
const labels = {
  person: "teacher",
  recording: "recording",
  recordings: "recordings",
  people: "people",
  allUnits: "All campuses",
};
const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

const typeNames: Record<ConversationType, { plural: string; singular: string; count: number }> = {
  teaching: { plural: "Teaching", singular: "Teaching", count: 128 },
  reception: { plural: "Reception", singular: "Reception", count: 46 },
  counselling: { plural: "Counselling", singular: "Counselling", count: 17 },
  meeting: { plural: "Meetings", singular: "Meeting", count: 12 },
  sales: { plural: "Sales", singular: "Sales", count: 11 },
};
const typeKeys = Object.keys(typeNames) as ConversationType[];

function Icon({ children, size = 18, stroke = 1.7 }: { children: ReactNode; size?: number; stroke?: number }) {
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
    >
      {children}
    </svg>
  );
}

const icons = {
  overview: (
    <Icon>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </Icon>
  ),
  recordings: (
    <Icon>
      <path d="M3 12h1M7 8v8M11 5v14M15 9v6M19 11v2" />
    </Icon>
  ),
  reviews: (
    <Icon>
      <path d="M4 5h16v11H9l-5 4z" />
      <path d="M9 10.5l2 2 4-4" />
    </Icon>
  ),
  people: (
    <Icon>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" />
      <path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c1.8.7 3 2.4 3.5 5.2" />
    </Icon>
  ),
  rubrics: (
    <Icon>
      <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" />
      <circle cx="16" cy="6" r="2" />
      <circle cx="10" cy="12" r="2" />
      <circle cx="18" cy="18" r="2" />
    </Icon>
  ),
  search: (
    <Icon size={16} stroke={1.8}>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </Icon>
  ),
  calendar: (
    <Icon size={16} stroke={1.8}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </Icon>
  ),
  upload: (
    <Icon size={16} stroke={2}>
      <path d="M12 16V4M7 9l5-5 5 5M4 16v4h16v-4" />
    </Icon>
  ),
  inbox: (
    <Icon size={24} stroke={1.8}>
      <path d="M12 16V4M7 9l5-5 5 5M4 16v4h16v-4" />
    </Icon>
  ),
};

interface RecordingRow {
  id: string;
  title: string;
  person: string;
  type: ConversationType;
  length: string;
  status: RecordingStatus;
  score: number | null;
  uploaded: string;
}

const recordings: RecordingRow[] = [
  {
    id: "r1",
    title: "Class 8 Science: Photosynthesis",
    person: "Anjali Sharma, Main campus",
    type: "teaching",
    length: "52:14",
    status: "analysed",
    score: 3.0,
    uploaded: "Today, 11:20",
  },
  {
    id: "r2",
    title: "Admission enquiry for Grade 3",
    person: "Front desk, Main campus",
    type: "reception",
    length: "06:48",
    status: "analysed",
    score: 4.2,
    uploaded: "Today, 10:05",
  },
  {
    id: "r3",
    title: "Class 10 Maths: Quadratic equations",
    person: "Rohit Meena, Vaishali Nagar",
    type: "teaching",
    length: "47:02",
    status: "transcribing",
    score: null,
    uploaded: "Today, 09:40",
  },
  {
    id: "r4",
    title: "Fee concession follow-up",
    person: "Front desk, Mansarovar",
    type: "reception",
    length: "04:12",
    status: "needs-review",
    score: null,
    uploaded: "Today, 09:12",
  },
  {
    id: "r5",
    title: "Parent meeting about attendance",
    person: "Neha Joshi, Counsellor",
    type: "counselling",
    length: "28:30",
    status: "analysed",
    score: 3.9,
    uploaded: "Yesterday",
  },
  {
    id: "r6",
    title: "Weekly academic council",
    person: "6 participants",
    type: "meeting",
    length: "41:55",
    status: "analysing",
    score: null,
    uploaded: "Yesterday",
  },
  {
    id: "r7",
    title: "ERP demo for a partner school",
    person: "Karan Singh, Sales",
    type: "sales",
    length: "33:10",
    status: "analysed",
    score: 2.8,
    uploaded: "10 Oct",
  },
];

const columns: TableColumn<RecordingRow>[] = [
  {
    key: "title",
    header: capitalise(labels.recording),
    render: (r) => (
      <>
        <a href="#" className="block font-semibold text-ink no-underline">
          {r.title}
        </a>
        <span className="text-small text-muted">{r.person}</span>
      </>
    ),
  },
  {
    key: "type",
    header: "Type",
    render: (r) => <TypeDot type={r.type} label={typeNames[r.type].singular} className="text-sm" />,
  },
  { key: "length", header: "Length", render: (r) => r.length },
  { key: "status", header: "Status", render: (r) => <StatusChip status={r.status} /> },
  {
    key: "score",
    header: "Score",
    align: "right",
    render: (r) => <ScoreChip score={r.score} variant="text" decimals={1} />,
  },
  { key: "uploaded", header: "Uploaded", align: "right", className: "text-muted", render: (r) => r.uploaded },
];

const metrics: Metric[] = [
  {
    id: "analysed",
    label: `${capitalise(labels.recordings)} analysed`,
    value: "214",
    foot: "32 more than last week",
    footTone: "success",
  },
  { id: "audio", label: "Audio processed", value: "162 h", foot: "41 h of silence removed" },
  {
    id: "median",
    label: "Median teaching score",
    value: "3.5",
    suffix: " / 5",
    foot: "Up 0.2 since September",
    footTone: "success",
  },
  { id: "disputed", label: "Scores disputed by staff", value: "7", foot: <a href="#">Review disputes</a> },
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
      <div className="flex flex-col gap-0.5">
        <NavItem href="#" icon={icons.overview}>
          Overview
        </NavItem>
        <NavItem href="/dev/components" icon={icons.recordings} current>
          Components
        </NavItem>
        <NavItem href="#" icon={icons.reviews} badge={7} badgeLabel="7 waiting">
          Reviews
        </NavItem>
        <NavItem href="#" icon={icons.people}>
          {capitalise(labels.people)}
        </NavItem>
        <NavItem href="#" icon={icons.rubrics}>
          Rubrics
        </NavItem>
      </div>
      <div className="flex flex-col gap-0.5">
        <div className="px-2.5 pb-1.5 text-caption font-semibold text-muted-2">Conversation types</div>
        {typeKeys.map((key) => (
          <NavItem key={key} href="#" type={key} count={typeNames[key].count}>
            {typeNames[key].plural}
          </NavItem>
        ))}
      </div>
    </nav>
  );
}

function Section({ title, note, children }: { title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <Panel title={title} description={note}>
      {children}
    </Panel>
  );
}

function Row({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-3">{children}</div>;
}

function RecentRecordings() {
  const [filter, setFilter] = useState<ConversationType | "all">("all");
  const rows = filter === "all" ? recordings : recordings.filter((r) => r.type === filter);
  return (
    <Panel
      flush
      title={`Recent ${labels.recordings}`}
      actions={
        <SegmentedControl
          label="Filter by type"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All" },
            ...typeKeys.map((key) => ({ value: key, label: typeNames[key].plural })),
          ]}
        />
      }
      footer={
        <>
          <span>
            Showing {rows.length} of {214}
          </span>
          <a href="#">View all {labels.recordings}</a>
        </>
      }
    >
      <Table
        caption={`Recent ${labels.recordings}`}
        captionHidden
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        empty={`No ${labels.recordings} of this type yet.`}
      />
    </Panel>
  );
}

function ToastTriggers() {
  const toast = useToast();
  return (
    <Row>
      <Button variant="secondary" onClick={() => toast.show({ title: "Saved", message: "Your changes are saved." })}>
        Show info toast
      </Button>
      <Button
        variant="secondary"
        onClick={() =>
          toast.show({
            tone: "success",
            title: `${capitalise(labels.recording)} shared`,
            message: `The ${labels.person} can see the report now.`,
          })
        }
      >
        Show success toast
      </Button>
      <Button
        variant="secondary"
        onClick={() =>
          toast.show({
            tone: "error",
            title: "Could not start the upload",
            message: "The storage link expired. Try again.",
            requestId: "req_01J9Z4K7X2M8",
          })
        }
      >
        Show error toast
      </Button>
    </Row>
  );
}

function FormControls() {
  const [consent, setConsent] = useState(false);
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-5">
      <Input label="School name" placeholder="For example, Greenfield Public School" />
      <Input label="Weight" defaultValue="120%" hint="Weights add up to 100%." error="Enter a number from 0 to 100." />
      <Select label="Campus" defaultValue="main">
        <option value="main">Main campus</option>
        <option value="vaishali">Vaishali Nagar</option>
        <option value="mansarovar">Mansarovar</option>
      </Select>
      <Select label={`${capitalise(labels.person)} or staff member`} disabled>
        <option>Match from file name</option>
      </Select>
      <Checkbox
        label={`Consent is on file for these ${labels.recordings}`}
        description="Required before analysis."
        checked={consent}
        onChange={(e) => setConsent(e.target.checked)}
      />
      <Checkbox label={`Show to ${labels.people}`} defaultChecked />
    </div>
  );
}

function Selectors() {
  const [period, setPeriod] = useState<"monthly" | "yearly">("monthly");
  return (
    <div className="flex flex-col gap-6">
      <SegmentedControl
        label="Billing period"
        className="self-start"
        value={period}
        onChange={setPeriod}
        options={[
          { value: "monthly", label: "Monthly" },
          { value: "yearly", label: "Yearly, 2 months free" },
        ]}
      />
      <Tabs
        label="Report sections"
        tabs={[
          { value: "summary", label: "Summary", panel: <p className="m-0 text-ink-2">Summary panel content.</p> },
          { value: "transcript", label: "Transcript", panel: <p className="m-0 text-ink-2">Transcript panel.</p> },
          { value: "evidence", label: "Evidence", panel: <p className="m-0 text-ink-2">Evidence panel.</p> },
        ]}
      />
    </div>
  );
}

function Skeletons() {
  const [loading, setLoading] = useState(true);
  return (
    <div className="flex flex-col gap-4">
      <Row>
        <Button variant="secondary" onClick={() => setLoading((l) => !l)}>
          {loading ? "Show content" : "Show loading state"}
        </Button>
      </Row>
      {loading ? (
        <SkeletonGroup label={`Loading ${labels.recordings}`} className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton className="h-8 w-8 rounded-full" />
              <div className="flex flex-1 flex-col gap-1.5">
                <Skeleton className="h-3.5 w-3/5" />
                <Skeleton className="h-3 w-2/5" />
              </div>
              <Skeleton className="h-6 w-20 rounded-full" />
            </div>
          ))}
        </SkeletonGroup>
      ) : (
        <p className="m-0 text-ink-2">Loaded content would replace the placeholders here.</p>
      )}
    </div>
  );
}

export default function ComponentsDemo() {
  return (
    <ToastProvider>
      <div className="flex min-h-screen flex-wrap">
        <Sidebar />
        <main className="flex min-w-0 flex-[999_1_560px] flex-col gap-6 px-[clamp(16px,3vw,40px)] pb-12 pt-7">
          <PageHeader
            title="Overview"
            description={`${labels.allUnits}, 6 to 12 October 2026`}
            actions={
              <>
                <Input
                  type="search"
                  label={`Search ${labels.recordings}`}
                  hideLabel
                  leadingIcon={icons.search}
                  placeholder={`Search ${labels.people}, topics, quotes`}
                  className="w-[270px] max-w-full"
                />
                <Button variant="secondary" icon={icons.calendar}>
                  Last 7 days
                </Button>
                <Button icon={icons.upload}>Upload {labels.recordings}</Button>
              </>
            }
          />
          <MetricStrip label="This week" metrics={metrics} />
          <RecentRecordings />

          <Card tone="warning">
            <h2 className="m-0 text-lg font-semibold">Component library (dev only)</h2>
            <p className="m-0 text-sm text-ink-2">
              Everything above is composed from <code>src/design</code> to compare with docs/design/01-overview.png.
              Decisions applied:
            </p>
            <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-sm text-ink-2">
              <li>
                Score colour bands use the UI v2 rule: below 3.0 danger, 3.0 to 3.7 warning, 3.8 and above success, on
                the one-decimal value shown (so 3.75 is success).
              </li>
              <li>
                Every control is at least 44px tall, including sidebar rows and segmented buttons (the design used
                32-40px there).
              </li>
              <li>
                Failed and Uploading chips are not in the design: Failed is danger on danger-tint, Uploading is
                primary-hover on primary-tint.
              </li>
            </ul>
          </Card>

          <Section title="Button" note="Primary, secondary and ghost; 44px minimum height; type=button by default.">
            <Row>
              <Button>Share report</Button>
              <Button variant="secondary">Export PDF</Button>
              <Button variant="ghost">21:05</Button>
              <Button icon={icons.upload}>Upload {labels.recordings}</Button>
              <Button disabled>Analyse 1 {labels.recording}</Button>
              <Button variant="secondary" disabled>
                Disabled
              </Button>
            </Row>
          </Section>

          <Section
            title="Input, Select, Checkbox, Label"
            note="Labels are linked to their controls; errors use aria-invalid and aria-describedby."
          >
            <FormControls />
          </Section>

          <Section title="StatusChip" note="The text carries the status; colour only reinforces it.">
            <Row>
              {(
                ["analysed", "transcribing", "analysing", "needs-review", "failed", "uploading"] as RecordingStatus[]
              ).map((s) => (
                <StatusChip key={s} status={s} />
              ))}
            </Row>
          </Section>

          <Section title="TypeDot" note="Names come from the tenant's labels.">
            <Row>
              {typeKeys.map((key) => (
                <TypeDot key={key} type={key} label={typeNames[key].singular} className="text-sm text-ink-2" />
              ))}
            </Row>
          </Section>

          <Section
            title="ScoreChip and ScoreBar"
            note="Bands: below 3.0 danger, 3.0 to 3.7 warning, 3.8 and above success."
          >
            <div className="flex flex-col gap-4">
              <Row>
                {[1, 2, 2.9, 3, 3.7, 3.75, 3.8, 5].map((s) => (
                  <ScoreChip key={s} score={s} decimals={Number.isInteger(s) ? 0 : 2} />
                ))}
                <ScoreChip score={null} />
              </Row>
              <Row>
                {[2.8, 3.0, 3.9, 4.2].map((s) => (
                  <ScoreChip key={s} score={s} variant="text" decimals={1} />
                ))}
                <ScoreChip score={null} variant="text" />
              </Row>
              <div className="flex flex-col gap-2">
                {[1, 2, 3, 4, 5].map((s) => (
                  <ScoreBar key={s} score={s} />
                ))}
              </div>
            </div>
          </Section>

          <Section
            title="SegmentedControl and Tabs"
            note="Segmented: role=group with aria-pressed. Tabs: tablist with arrow keys."
          >
            <Selectors />
          </Section>

          <Section
            title="ProgressBar"
            note="role=progressbar with a label and values; the fill animates only without reduced motion."
          >
            <div className="flex max-w-[520px] flex-col gap-4">
              <ProgressBar label="Uploading Front desk, morning shift.mp3" value={62} />
              <ProgressBar
                label="Class 9 English, Poetry, 13 Oct.m4a"
                value={100}
                tone="success"
                showLabel
                valueText="Ready"
              />
              <ProgressBar
                label="Annual day, full programme.wav"
                value={12}
                tone="danger"
                showLabel
                valueText="Failed"
              />
              <ProgressBar label="Plan hours used this month" value={38.4} showLabel valueText="38.4 of 100" />
            </div>
          </Section>

          <Section title="Card" note="Tones from the processing stage cards.">
            <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2 p-0">
              {(
                [
                  ["plain", "Plain", 0],
                  ["neutral", "Uploading", 3],
                  ["active", "Transcribing", 5],
                  ["warning", "Needs review", 2],
                ] as const
              ).map(([tone, name, count]) => (
                <Card key={tone} as="li" tone={tone}>
                  <span className="flex items-baseline justify-between">
                    <span className="text-sm text-ink-2">{name}</span>
                    <span className="text-2xl font-semibold tabular-nums">{count}</span>
                  </span>
                  <span className="text-caption text-muted">tone=&quot;{tone}&quot;</span>
                </Card>
              ))}
            </ol>
          </Section>

          <Section title="EmptyState">
            <EmptyState
              icon={icons.inbox}
              title={`No ${labels.recordings} yet`}
              description={`Upload a ${labels.recording} and the report appears here once it is analysed.`}
              action={<Button>Upload {labels.recordings}</Button>}
            />
          </Section>

          <Section
            title="Toast"
            note="Info and success go to a polite status region; errors to an alert region and stay until dismissed."
          >
            <div className="flex flex-col gap-4">
              <ToastTriggers />
              <div className="flex max-w-[380px] flex-col gap-2">
                <Toast title="Saved" message="Your changes are saved." onDismiss={() => undefined} />
                <Toast tone="success" title="Rubric published" onDismiss={() => undefined} />
                <Toast
                  tone="error"
                  title="Could not load the report"
                  message="Something went wrong on our side."
                  requestId="req_01J9Z4K7X2M8"
                  onDismiss={() => undefined}
                />
              </div>
            </div>
          </Section>

          <Section
            title="PageHeader with breadcrumbs"
            note="The page title is an h1; this copy uses titleAs=h2 so the page keeps one h1."
          >
            <div className="rounded-card border border-line-subtle bg-page p-5">
              <PageHeader
                title="Upload recordings"
                titleAs="h2"
                breadcrumbs={[{ label: capitalise(labels.recordings), href: "#" }, { label: "Upload" }]}
                description="Files go straight to encrypted storage in India."
                actions={<Button variant="secondary">Cancel</Button>}
              />
            </div>
          </Section>

          <Section
            title="Skeleton"
            note="aria-hidden blocks inside an aria-busy container; shimmer only without reduced motion."
          >
            <Skeletons />
          </Section>
        </main>
      </div>
    </ToastProvider>
  );
}
