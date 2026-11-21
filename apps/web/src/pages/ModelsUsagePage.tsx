// Models & usage (owner's request, 2026-11-20): what each AI model cost this organisation over 30 days, and the credit
// left where the provider reports it. Pictures first, few words (manager's glance feedback). Every number comes
// from GET /v1/models-usage (measured, golden rule 6); a provider without a balance API gets a link, never a guess.

import { useModelsUsage } from "../api/hooks";
import type { ModelUsage, ModelsUsage, ProviderBalance } from "../api/types";
import { EmptyState, MetricStrip, PageHeader, Panel, Skeleton } from "../design";

const inr = (v: number | null | undefined, digits = 0) =>
  v == null ? "—" : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;

const compact = (n: number) => n.toLocaleString("en-IN", { notation: "compact", maximumFractionDigits: 1 });

const PROVIDER_NAMES: Record<string, string> = {
  openai: "OpenAI",
  gemini: "Gemini",
  sarvam: "Sarvam",
  deepgram: "Deepgram",
  groq: "Groq",
  qwen: "Qwen",
  aws: "AWS",
};

const providerName = (p: string) => PROVIDER_NAMES[p] ?? p;

const SPEECH = "bg-primary";
const SCORING = "bg-type-support";

export function ModelsUsagePage() {
  const query = useModelsUsage();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Models & usage" description="AI spend over the last 30 days, and credit left." />
      {query.isPending && <Skeleton className="h-64" />}
      {query.isError && <EmptyState title="Couldn't load usage" description="Please try again in a moment." />}
      {query.data && <Body data={query.data} />}
    </div>
  );
}

function Body({ data }: { data: ModelsUsage }) {
  const speech = data.models.filter((m) => m.kind === "speech");
  const llm = data.models.filter((m) => m.kind === "llm");
  const minutes = speech.reduce((sum, m) => sum + (m.minutes ?? 0), 0);
  const tokens = llm.reduce((sum, m) => sum + (m.tokens_in ?? 0) + (m.tokens_out ?? 0), 0);
  return (
    <>
      <Credits balances={data.balances} />
      <MetricStrip
        label="Last 30 days"
        metrics={[
          { id: "total", label: "Spent, 30 days", value: inr(data.total_inr) },
          {
            id: "speech",
            label: <Legend tone={SPEECH} text="Speech to text" />,
            value: inr(data.speech_inr),
            foot: `${compact(minutes)} min of audio`,
            footTone: "muted",
          },
          {
            id: "llm",
            label: <Legend tone={SCORING} text="Scoring (LLM)" />,
            value: inr(data.llm_inr),
            foot: `${compact(tokens)} tokens`,
            footTone: "muted",
          },
          { id: "models", label: "Models used", value: data.models.length },
        ]}
      />
      <Panel title="Spend per day">
        <DailyChart daily={data.daily} />
      </Panel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Speech-to-text models">
          <ModelBars models={speech} tone={SPEECH} />
        </Panel>
        <Panel title="Scoring models">
          <ModelBars models={llm} tone={SCORING} />
        </Panel>
      </div>
    </>
  );
}

function Legend({ tone, text }: { tone: string; text: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-2.5 w-2.5 rounded-sm ${tone}`} aria-hidden />
      {text}
    </span>
  );
}

function Credits({ balances }: { balances: ProviderBalance[] }) {
  if (!balances.length) return null;
  return (
    <section aria-labelledby="api-credits" className="flex flex-col gap-3">
      <h2 id="api-credits" className="text-[15px] font-semibold text-ink">
        API key credits
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {balances.map((b) => (
          <a
            key={b.provider}
            href={b.console_url}
            target="_blank"
            rel="noreferrer"
            className="group flex flex-col gap-2 rounded-xl border border-line bg-surface p-4 no-underline hover:border-primary-border"
          >
            <span className="flex items-center justify-between text-[13px] text-muted">
              {b.name}
              <span
                className={`h-2 w-2 rounded-full ${b.configured ? "bg-success" : "bg-track"}`}
                title={b.configured ? "Key set" : "No key set"}
              />
            </span>
            {b.amount != null ? (
              <span className="text-[26px] font-semibold text-ink">
                {b.currency === "USD" ? "$" : ""}
                {b.amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                {b.currency && b.currency !== "USD" ? ` ${b.currency}` : ""}
              </span>
            ) : (
              <span className="text-[15px] font-medium text-primary group-hover:underline">See balance ↗</span>
            )}
            <span className="text-[12px] text-muted">
              {b.amount != null
                ? "Credit left on this key"
                : (b.note ?? (b.configured ? "Shown on their site" : "Not set up"))}
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}

function DailyChart({ daily }: { daily: ModelsUsage["daily"] }) {
  const max = Math.max(...daily.map((d) => d.speech_inr + d.llm_inr), 0);
  if (max === 0) return <p className="text-sm text-muted">No AI use in the last 30 days.</p>;
  const label = (day: string) =>
    new Date(`${day}T00:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return (
    <div>
      <div className="flex h-44 items-end gap-[3px]" role="img" aria-label="Spend per day, last 30 days">
        {daily.map((d) => {
          const total = d.speech_inr + d.llm_inr;
          return (
            <div
              key={d.day}
              className="group relative flex h-full flex-1 flex-col justify-end"
              title={`${label(d.day)}: ${inr(total, 2)} (speech ${inr(d.speech_inr, 2)}, scoring ${inr(d.llm_inr, 2)})`}
            >
              {total === 0 ? (
                <div className="h-[3px] rounded-sm bg-track" />
              ) : (
                <div
                  className="flex flex-col overflow-hidden rounded-t-sm"
                  style={{ height: `${(total / max) * 100}%` }}
                >
                  <div className={SCORING} style={{ flexGrow: d.llm_inr }} />
                  <div className={SPEECH} style={{ flexGrow: d.speech_inr }} />
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-[12px] text-muted">
        <span>{label(daily[0]?.day ?? "")}</span>
        <span>Peak {inr(max)}</span>
        <span>Today</span>
      </div>
    </div>
  );
}

function ModelBars({ models, tone }: { models: ModelUsage[]; tone: string }) {
  if (!models.length) return <p className="text-sm text-muted">Not used in the last 30 days.</p>;
  const max = Math.max(...models.map((m) => m.inr ?? 0), 0.0001);
  return (
    <ul className="flex flex-col gap-4">
      {models.map((m) => (
        <li key={`${m.provider}/${m.model}`} className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate font-medium text-ink">
              {providerName(m.provider)} <span className="font-normal text-muted">{m.model}</span>
            </span>
            <span className="shrink-0 font-semibold text-ink">{inr(m.inr, 2)}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-track">
            <div className={`h-full rounded-full ${tone}`} style={{ width: `${((m.inr ?? 0) / max) * 100}%` }} />
          </div>
          <div className="text-[12px] text-muted">
            {m.kind === "speech"
              ? `${m.runs} runs · ${compact(m.minutes ?? 0)} min`
              : `${compact(m.runs)} calls · ${compact((m.tokens_in ?? 0) + (m.tokens_out ?? 0))} tokens`}
            {m.errors ? ` · ${m.errors} failed` : ""}
          </div>
        </li>
      ))}
    </ul>
  );
}
