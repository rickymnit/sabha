// /phone-calls (ADR 0017): answered calls from MyOperator, newest first, for owners, admins and managers. Each call
// can be played from MyOperator, and "Analyse" turns it into a recording that goes through the usual analysis.
// The first time one of an agent's calls is analysed, the page asks who the agent is in Sabha; after that their
// calls start straight away.

import { useMemo, useState, type FormEvent } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { ApiError } from "../api/client";
import {
  useAnalysePhoneCall,
  usePeople,
  usePhoneAgents,
  usePhoneCallAudio,
  usePhoneCalls,
  useSpeechModels,
} from "../api/hooks";
import type { Me, PhoneCallItem } from "../api/types";
import { capitalise, formatDateTime, formatWhen, statusChip } from "../app/format";
import { rememberedModel, speechFields, type SpeechValue } from "../features/speech/models";
import { SpeechChoices } from "../features/speech/SpeechChoices";
import {
  Button,
  Dialog,
  EmptyState,
  Icon,
  Input,
  MetricStrip,
  PageHeader,
  Panel,
  SegmentedControl,
  Select,
  Skeleton,
  SkeletonGroup,
  StatusChip,
  Table,
  useToast,
} from "../design";

type CallType = "support" | "sales";
/** What the Analyse window decided: the type, who the agent is (when not linked yet) and the speech choices. */
interface Choice {
  type: CallType;
  personId?: string;
  newPerson?: { name: string; unit_id: string };
  speech?: Record<string, unknown>;
}
/** The one scoring model set up (packages/llm: LLM_MODEL_MID); shown, not chosen. */
const SCORING_MODEL = "OpenAI GPT-6 Luna";
const NEW = "__new__";

const PERIODS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "", label: "All calls" },
];

function since(days: string): string | null {
  return days ? new Date(Date.now() - Number(days) * 86_400_000).toISOString() : null;
}

/** "4:30", "1:02:05". */
function callLength(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** What a call is analysed as when nobody is asked: a sales department's calls are sales calls, the rest support. */
const TIME = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit" });

/** ["Today", "12:48 pm"], ["18 Nov", "9:05 am"]: the day as the rest of the app says it, then the time. */
function when(iso: string): [string, string] {
  return [formatWhen(iso).split(",")[0] ?? "", TIME.format(new Date(iso))];
}

function guessType(call: PhoneCallItem, enabled: string[]): CallType {
  const sales = /sales/i.test(call.department ?? "") && enabled.includes("sales");
  return sales || !enabled.includes("support") ? "sales" : "support";
}

function problem(error: unknown): { message: string; requestId?: string } {
  if (error instanceof ApiError) return { message: error.message, requestId: error.requestId };
  return { message: "Something went wrong. Please try again." };
}

export function PhoneCallsPage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const toast = useToast();
  const [agent, setAgent] = useState("");
  const [direction, setDirection] = useState<"" | "incoming" | "outgoing">("");
  const [show, setShow] = useState<"" | "yes" | "no">("");
  const [period, setPeriod] = useState("30");
  const [from] = useState(() => new Map<string, string | null>());
  if (!from.has(period)) from.set(period, since(period));
  const calls = usePhoneCalls({
    agent: agent || null,
    direction: direction || null,
    analysed: show ? show === "yes" : null,
    from: from.get(period) ?? null,
  });
  const agents = usePhoneAgents();
  const audio = usePhoneCallAudio();
  const analyse = useAnalysePhoneCall();
  const [playing, setPlaying] = useState<{ id: string; url: string } | null>(null);
  const [asking, setAsking] = useState<PhoneCallItem | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const rows = calls.data?.pages.flatMap((page) => page.items) ?? [];
  const filtered = Boolean(agent || direction || show || period !== "30");
  const manager = me.user.role === "manager";
  const types = me.tenant.enabled_types.filter((t): t is CallType => t === "support" || t === "sales");

  const totals = useMemo(() => {
    const list = agents.data ?? [];
    return {
      calls: list.reduce((sum, a) => sum + a.calls, 0),
      analysed: list.reduce((sum, a) => sum + a.analysed, 0),
      agents: list.length,
      matched: list.filter((a) => a.person).length,
    };
  }, [agents.data]);

  const play = (call: PhoneCallItem) => {
    if (playing?.id === call.id) return;
    audio.mutate(call.id, {
      onSuccess: ({ url }) => setPlaying({ id: call.id, url }),
      onError: (error) => {
        const { message, requestId } = problem(error);
        toast.show({ tone: "error", title: "We couldn't play this call", message, requestId });
      },
    });
  };

  const start = (call: PhoneCallItem, choice: Choice, onDone?: () => void) => {
    setBusy(call.id);
    analyse.mutate(
      { callId: call.id, ...choice },
      {
        onSuccess: () => {
          onDone?.();
          toast.show({
            tone: "success",
            title: "Analysis started",
            message: `The report on ${call.agents[0]?.name ?? "this"}'s call will be ready in a few minutes.`,
            duration: 6_000,
          });
        },
        onError: (error) => {
          const { message, requestId } = problem(error);
          toast.show({ tone: "error", title: "We couldn't start the analysis", message, requestId });
        },
        onSettled: () => setBusy(null),
      },
    );
  };

  const onAnalyse = (call: PhoneCallItem) => {
    // "Try again" after a failed fetch sends the same recording again; otherwise choose how to analyse first.
    if (call.import_error) start(call, { type: guessType(call, types) });
    else setAsking(call);
  };

  const clear = () => {
    setAgent("");
    setDirection("");
    setShow("");
    setPeriod("30");
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Phone calls"
        description="Answered calls from MyOperator, newest first. Listen to any call, or press Analyse to score it."
      />
      {agents.isSuccess && totals.calls > 0 && (
        <MetricStrip
          label="Phone calls at a glance"
          metrics={[
            { id: "calls", label: "Recorded calls", value: totals.calls.toLocaleString("en-IN") },
            {
              id: "analysed",
              label: "Sent for analysis",
              value: totals.analysed.toLocaleString("en-IN"),
              foot: totals.analysed ? undefined : "Press Analyse on any call",
              footTone: "muted",
            },
            {
              id: "agents",
              label: "Agents",
              value: totals.agents,
              foot: `${totals.matched} of ${totals.agents} linked to ${labels.person_plural.toLowerCase()}`,
              footTone: totals.matched === totals.agents ? "success" : "muted",
            },
          ]}
        />
      )}
      <Panel
        flush
        aria-label="Phone calls"
        actions={
          <div className="flex flex-wrap items-end gap-3">
            <Select label="Agent" value={agent} onChange={(e) => setAgent(e.target.value)} className="w-52">
              <option value="">Everyone</option>
              {(agents.data ?? []).map((a) => (
                <option key={a.user_id} value={a.user_id}>
                  {a.name}
                  {a.extension ? ` (ext ${a.extension})` : ""}
                </option>
              ))}
            </Select>
            <Select
              label="Direction"
              value={direction}
              onChange={(e) => setDirection(e.target.value as typeof direction)}
              className="w-40"
            >
              <option value="">Both</option>
              <option value="incoming">Incoming</option>
              <option value="outgoing">Outgoing</option>
            </Select>
            <Select label="Show" value={show} onChange={(e) => setShow(e.target.value as typeof show)} className="w-44">
              <option value="">All calls</option>
              <option value="no">Not analysed</option>
              <option value="yes">Analysed</option>
            </Select>
            <Select label="When" value={period} onChange={(e) => setPeriod(e.target.value)} className="w-40">
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </Select>
          </div>
        }
        footer={
          calls.isSuccess &&
          rows.length > 0 && (
            <div className="flex items-center justify-between gap-3">
              <span>
                {rows.length} {rows.length === 1 ? "call" : "calls"}
                {calls.hasNextPage ? " so far" : ""}
              </span>
              {calls.hasNextPage && (
                <Button
                  variant="secondary"
                  onClick={() => void calls.fetchNextPage()}
                  disabled={calls.isFetchingNextPage}
                >
                  {calls.isFetchingNextPage ? "Loading…" : "Show older"}
                </Button>
              )}
            </div>
          )
        }
      >
        {calls.isError ? (
          <EmptyState
            headingAs="h3"
            icon={<Icon name="alert" size={26} />}
            title="We couldn't load the calls"
            description={`Please try again in a moment.${calls.error instanceof ApiError && calls.error.requestId ? ` If it keeps happening, quote reference ${calls.error.requestId}.` : ""}`}
            action={<Button onClick={() => void calls.refetch()}>Try again</Button>}
          />
        ) : calls.isPending ? (
          <SkeletonGroup label="Loading calls" className="flex flex-col gap-4 px-5 py-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-4 w-full max-w-2xl" />
            ))}
          </SkeletonGroup>
        ) : (
          <Table<PhoneCallItem>
            aria-label="Phone calls"
            rows={rows}
            rowKey={(call) => call.id}
            minWidth={0}
            empty={
              <EmptyState
                headingAs="h3"
                className="py-12"
                icon={<Icon name="phone" size={26} />}
                title={filtered ? "No calls match these filters" : "No calls yet"}
                description={
                  filtered
                    ? undefined
                    : manager
                      ? `Calls appear here once their agents are linked to ${labels.person_plural.toLowerCase()} in your ${labels.unit.toLowerCase()}. An owner or admin links an agent the first time they analyse one of the agent's calls.`
                      : "Answered calls from MyOperator appear here within about ten minutes."
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
                className: "whitespace-nowrap",
                render: (call) => {
                  const [day, time] = when(call.started_at);
                  return (
                    <time dateTime={call.started_at} title={formatDateTime(call.started_at)}>
                      <span className="block text-ink">{day}</span>
                      <span className="block text-caption text-muted-2">{time}</span>
                    </time>
                  );
                },
              },
              {
                key: "agent",
                header: "Agent",
                render: (call) => {
                  const first = call.agents[0];
                  const others = call.agents.length - 1;
                  return (
                    <div className="flex flex-col">
                      <span className="font-semibold text-ink">{first?.name ?? "Unknown"}</span>
                      <span className="text-caption text-muted-2">
                        {[
                          call.department,
                          first?.extension ? `ext ${first.extension}` : null,
                          others > 0 ? `+${others} colleague${others > 1 ? "s" : ""}` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </div>
                  );
                },
              },
              {
                key: "customer",
                header: "Customer",
                hideOnPhone: true,
                className: "whitespace-nowrap",
                render: (call) => (
                  <div className="flex flex-col">
                    <span className="tabular-nums text-ink">{call.customer}</span>
                    <span className="text-caption text-muted-2">{capitalise(call.direction)}</span>
                  </div>
                ),
              },
              {
                key: "length",
                header: "Length",
                align: "right",
                className: "whitespace-nowrap tabular-nums",
                render: (call) => callLength(call.duration_s),
              },
              {
                key: "listen",
                header: "Listen",
                render: (call) =>
                  playing?.id === call.id ? (
                    <audio
                      controls
                      autoPlay
                      src={playing.url}
                      className="h-10 w-56 max-w-full"
                      aria-label={`Call with ${call.customer}`}
                    />
                  ) : (
                    <Button
                      variant="ghost"
                      onClick={() => play(call)}
                      disabled={audio.isPending && audio.variables === call.id}
                      aria-label={`Play the call with ${call.customer}, ${formatDateTime(call.started_at)}`}
                    >
                      <Icon name="mic" size={16} />
                      {audio.isPending && audio.variables === call.id ? "Loading…" : "Play"}
                    </Button>
                  ),
              },
              {
                key: "analysis",
                header: "Analysis",
                render: (call) => <AnalysisCell call={call} busy={busy === call.id} onAnalyse={onAnalyse} />,
              },
            ]}
          />
        )}
      </Panel>
      {asking && (
        <AnalyseDialog
          call={asking}
          types={types}
          personWord={labels.person}
          unitWord={labels.unit}
          units={me.tenant.units}
          isAdmin={me.user.role === "owner" || me.user.role === "admin"}
          sending={busy === asking.id}
          onClose={() => setAsking(null)}
          onSubmit={(choice) => start(asking, choice, () => setAsking(null))}
        />
      )}
    </div>
  );
}

function AnalysisCell({
  call,
  busy,
  onAnalyse,
}: {
  call: PhoneCallItem;
  busy: boolean;
  onAnalyse: (call: PhoneCallItem) => void;
}) {
  if (call.import_error) {
    return (
      <div className="flex flex-col items-start gap-1">
        <span className="text-caption text-danger" title={call.import_error}>
          Couldn't fetch the recording
        </span>
        <Button variant="secondary" onClick={() => onAnalyse(call)} disabled={busy}>
          {busy ? "Starting…" : "Try again"}
        </Button>
      </div>
    );
  }
  if (!call.analysis) {
    return (
      <Button variant="secondary" onClick={() => onAnalyse(call)} disabled={busy} aria-label={`Analyse this call`}>
        {busy ? "Starting…" : "Analyse"}
      </Button>
    );
  }
  const { chip, text } = statusChip(call.analysis.status);
  const label = call.analysis.status === "CREATED" ? "Fetching audio" : text;
  return (
    <div className="flex flex-col items-start gap-1">
      <StatusChip status={chip}>{label}</StatusChip>
      {call.analysis.status !== "CREATED" && (
        <Link to={`/recordings/${encodeURIComponent(call.analysis.recording_id)}`} className="text-caption">
          {call.analysis.status === "COMPLETED" ? "Open report" : "View progress"}
        </Link>
      )}
    </div>
  );
}

function AnalyseDialog({
  call,
  types,
  personWord,
  unitWord,
  units,
  isAdmin,
  sending,
  onClose,
  onSubmit,
}: {
  call: PhoneCallItem;
  types: CallType[];
  personWord: string;
  unitWord: string;
  units: Me["tenant"]["units"];
  /** Owners and admins: choose the transcription model and add new people. */
  isAdmin: boolean;
  sending: boolean;
  onClose: () => void;
  onSubmit: (choice: Choice) => void;
}) {
  const people = usePeople();
  const models = useSpeechModels(isAdmin);
  const agent = call.agents[0]?.name ?? "this agent";
  const linked = call.person;
  const word = personWord.toLowerCase(); // mid-sentence; the workspace's labels are capitalised
  const unitText = unitWord.toLowerCase();
  const [personId, setPersonId] = useState("");
  const [name, setName] = useState(call.agents[0]?.name ?? "");
  const [unitId, setUnitId] = useState("");
  const [type, setType] = useState<CallType>(guessType(call, types));
  const helpers = new Set(call.agents.slice(1).map((a) => a.user_id)).size > 0;
  const [speech, setSpeech] = useState<SpeechValue>({
    asrModel: "",
    speakers: "2",
    speakerModel: "pyannote",
    transferred: helpers,
  });
  const [error, setError] = useState<string | null>(null);
  const adding = personId === NEW;
  const support = type === "support";
  const modelList = isAdmin ? models.data : undefined;
  // The model last chosen on this device (as on Upload) until someone picks one here.
  const value = { ...speech, asrModel: speech.asrModel || (modelList ? rememberedModel(modelList) : "") };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!linked && !personId) return setError(`Choose which ${word} ${agent} is.`);
    if (adding && !name.trim()) return setError("Type the name to add.");
    if (adding && !unitId) return setError(`Choose the ${unitText} to add ${name.trim()} to.`);
    onSubmit({
      type,
      ...(linked ? {} : adding ? { newPerson: { name: name.trim(), unit_id: unitId } } : { personId }),
      speech: speechFields(value, support, Boolean(modelList)),
    });
  };

  return (
    <Dialog
      title="Analyse this call"
      description={
        <p className="m-0">
          {linked
            ? `${agent}'s call (${linked.name} in Sabha), ${callLength(call.duration_s)} long. Choose how to analyse it.`
            : `Choose the ${word} in Sabha who answers calls as ${agent}; Sabha remembers this for ${agent}'s other calls. Then choose how to analyse it.`}
        </p>
      }
      onClose={onClose}
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {!linked && (
          <Select
            label={capitalise(personWord)}
            value={personId}
            onChange={(e) => {
              setPersonId(e.target.value);
              setError(null);
            }}
            disabled={!people.isSuccess}
          >
            <option value="">{people.isPending ? "Loading…" : `Choose a ${word}`}</option>
            {(people.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
            {isAdmin && (
              <option value={NEW}>
                + Add {agent} as a new {word}
              </option>
            )}
          </Select>
        )}
        {adding && (
          <div className="flex flex-col gap-4 rounded-card bg-surface-subtle p-4">
            <Input label="Name" value={name} onChange={(e) => setName(e.target.value.slice(0, 120))} />
            <Select
              label={capitalise(unitWord)}
              value={unitId}
              onChange={(e) => {
                setUnitId(e.target.value);
                setError(null);
              }}
            >
              <option value="">Choose a {unitText}</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </Select>
          </div>
        )}
        {types.length > 1 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-ink">Analyse as</span>
            <SegmentedControl<CallType>
              label="Analyse as"
              value={type}
              onChange={setType}
              options={types.map((t) => ({ value: t, label: t === "support" ? "Support call" : "Sales call" }))}
            />
          </div>
        )}
        <SpeechChoices value={value} onChange={setSpeech} models={modelList} support={support} personWord={word} />
        <p className="m-0 text-caption text-muted">
          Scoring: {SCORING_MODEL}, the scoring model set up for Sabha. Every score quotes the call.
        </p>
        {error && (
          <p role="alert" className="m-0 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={sending || (isAdmin && models.isPending)}>
            {sending ? "Starting…" : "Analyse"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
