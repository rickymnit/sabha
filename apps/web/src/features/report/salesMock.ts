// A fictional sales phone call for the /dev/report demo and tests (UI v2 sales report): every name, company and line
// is made up. Scored on the sales rubric v0.3 (weights 5/25/25/25/5/15), with a deal card and computed metrics.

import type { Transcript, Utterance } from "../transcript";
import type { AnalysisReport, CardEvidence, EvidenceQuote, Labels, VerifiedDimension } from "./types";
import type { MockLesson } from "./mock";

export const salesLabels: Labels = {
  person: "Sales rep",
  person_plural: "Sales reps",
  recording: "Call",
  recording_plural: "Calls",
  unit: "Team",
  manager: "Manager",
};

const LINES: [role: "sales_rep" | "customer", startS: number, endS: number, text: string][] = [
  ["customer", 2, 9, "Hello, I saw your biometric attendance ad. We need something for our three centres."],
  ["sales_rep", 10, 18, "Yes sir, we have fingerprint and face models. How many staff per centre?"],
  ["customer", 19, 31, "Around forty at each. We do not have a central server, everything is separate."],
  ["sales_rep", 32, 44, "Okay, okay. Our cloud model works without a server, it syncs on mobile data."],
  ["customer", 45, 58, "What about reports? Abhi hum register mein likhte hain, month end pe Excel banate hain."],
  ["sales_rep", 59, 70, "Reports are there, monthly and daily, all in the app."],
  ["customer", 71, 83, "Is the price negotiable? Three centres ka total bahut ho jayega."],
  ["sales_rep", 84, 96, "Sir, for three units I can give you ten percent off, that is the best price."],
  ["customer", 97, 106, "Ultra basic model we want, just fingerprint, and any time we can download the report."],
  ["sales_rep", 107, 121, "Basic model is fine. I will send the details on WhatsApp, then the quotation."],
  ["customer", 122, 130, "Okay, send it. If the price works we will go ahead."],
  ["sales_rep", 131, 140, "Sure sir, I will send it today. Thank you."],
];

function transcript(): Transcript {
  const utterances: Utterance[] = LINES.map(([role, start, end, text]) => ({
    role,
    speaker_label: role === "sales_rep" ? "SPEAKER_00" : "SPEAKER_01",
    start_ms: start * 1000,
    end_ms: end * 1000,
    text,
    avg_confidence: 0.92,
    low_confidence_spans: [],
  }));
  return {
    version: "transcript@v1",
    timeline: "original",
    asr_model: "demo",
    word_count: utterances.reduce((n, u) => n + u.text.split(" ").length, 0),
    utterances,
  };
}

const at = (index: number, part?: string): EvidenceQuote & CardEvidence => {
  const [, start, end, text] = LINES[index] as (typeof LINES)[number];
  return {
    quote: part ?? text,
    utterance_id: `u${String(index).padStart(4, "0")}`,
    start_ms: start * 1000,
    end_ms: end * 1000,
  };
};

export function mockSalesCall(): MockLesson {
  return {
    transcript: transcript(),
    labels: salesLabels,
    roles: { sales_rep: { label: "Sales rep", analysed: true }, customer: { label: "Customer" } },
    recording: {
      id: "rec_demo_sales",
      title: "Biometric attendance enquiry",
      type_label: "Sales",
      person: { id: "per_demo_sales", name: "Rohit Meena", unit: "West team" },
      recorded_at: "2026-10-26T06:10:00Z",
      duration_ms: 160_000,
      speech_ms: 148_000,
      languages: ["English", "Hindi"],
      removed_silence: [],
    },
  };
}

const dimension = (
  key: string,
  name: string,
  weight: number,
  score: number,
  rationale: string,
  evidence: EvidenceQuote[],
  suggestion: string,
): VerifiedDimension => ({ key, name, weight, verified: true, score, rationale, evidence, suggestion });

export function mockSalesReport(): AnalysisReport {
  return {
    status: "completed",
    reasons: [],
    analysis_id: "an_demo_sales",
    recording_id: "rec_demo_sales",
    created_at: "2026-10-26T06:20:00Z",
    rubric: { id: "sales.company.v0.3", version: "0.3", name: "Sales" },
    model: { ids: ["demo"] },
    overall: 2.1,
    person_history: { count: 10, min: 2.4, max: 3.9 },
    dimensions: [
      dimension(
        "opening_and_positioning",
        "Opening and positioning",
        0.05,
        1,
        "The rep did not introduce himself or the company.",
        [at(1)],
        "Open with your name, the company and one line on what you do for centres like theirs.",
      ),
      dimension(
        "discovery",
        "Discovering the customer's situation",
        0.25,
        3,
        "Asked about the setup, not how attendance is tracked today.",
        [at(1), at(4)],
        "Ask how attendance is recorded and reported today before recommending a model.",
      ),
      dimension(
        "pains_to_value",
        "Turning problems into value",
        0.25,
        2,
        "Heard the need but did not link it to a benefit.",
        [at(4), at(5)],
        "Tie the month-end Excel work to the reports the app makes on its own.",
      ),
      dimension(
        "differentiation",
        "Showing the difference",
        0.25,
        1,
        "Never said why our system suits a basic setup with no central server.",
        [at(8, "Ultra basic model we want, just fingerprint, and any time we can download the report")],
        "Connect the product to what they asked for: three sites, no central server, reports any time.",
      ),
      dimension(
        "price_and_objections",
        "Price and objections",
        0.05,
        1,
        "The price question was answered with a discount, not value.",
        [at(7)],
        "When they ask if the price is negotiable, explain the value first, then the options.",
      ),
      dimension(
        "next_step_commitment",
        "Booked next step",
        0.15,
        3,
        "WhatsApp follow-up agreed, but no date.",
        [at(9)],
        "Agree a day and time to go through the quotation together.",
      ),
    ],
    metrics: [
      { key: "duration_s", name: "Length", value: 160, unit: "count", definition: "Length of the call." },
      {
        key: "sales_rep_talk_share",
        name: "Sales rep talk",
        value: 0.52,
        unit: "ratio",
        definition: "Share of speech.",
      },
      { key: "customer_talk_share", name: "Customer talk", value: 0.48, unit: "ratio", definition: "Share of speech." },
      { key: "sales_rep_question_count", name: "Questions asked", value: 1, unit: "count", definition: "Questions." },
      { key: "open_question_ratio", name: "Open questions", value: 1, unit: "ratio", definition: "Open questions." },
      {
        key: "longest_monologue_s",
        name: "Longest monologue",
        value: 14_000,
        unit: "ms",
        definition: "Longest stretch of the rep talking.",
        range: { start_ms: 107_000, end_ms: 121_000 },
      },
    ],
    summary:
      "Rohit learned what the customer wants, but did not show why our product fits or answer the price question.",
    strengths: ["Found the need: fingerprint attendance at 3 locations", "Agreed a next step on WhatsApp"],
    gaps: ["No link from the need to a benefit", "Price answered with a discount"],
    suggestions: [
      { text: "Ask what they need to do with attendance data before recommending a model.", ...at(5) },
      { text: "When they ask if the price is negotiable, explain the value first, then the options.", ...at(6) },
      { text: "Agree a date for going through the quotation.", ...at(9) },
    ],
    deal_card: {
      current_setup: [{ fact: "Paper registers, typed into Excel at month end", evidence: at(4) }],
      customer_needs: [
        { need: "Fingerprint attendance at 3 locations", evidence: at(0) },
        { need: "Basic setup with no central server, reports any time", evidence: at(8) },
      ],
      objections: [
        {
          objection: "Price negotiation",
          response: "Offered ten percent off for three units.",
          settled: "no",
          evidence: at(6),
        },
      ],
      interest_level: { value: "medium", evidence: at(10) },
      next_step: { action: "Details by WhatsApp, then a quote", owner: "sales_rep", due: null, evidence: at(9) },
      left_out: 0,
    },
  };
}
