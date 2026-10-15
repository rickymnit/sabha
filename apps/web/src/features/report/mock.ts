// Mock report data for the demo page and tests, until the analysis API (P5.7b) exists. Built on the P6.5 mock
// transcript: every quote is text from an utterance of that transcript and carries that utterance's id and times,
// and every metric is counted from it here (as P5.5 will in Python). Names and details are fictional.

import { formatClock, type RoleLabels, type Transcript, type Utterance } from "../transcript";
import { generateMockTranscript } from "../transcript/mock";
import type {
  AnalysisFailed,
  AnalysisNeedsReview,
  AnalysisProcessing,
  AnalysisReport,
  Dimension,
  EvidenceQuote,
  Labels,
  Metric,
  ReportRecording,
  Suggestion,
  TimeRange,
  UnverifiedDimension,
  VerifiedDimension,
} from "./types";

/** Stand-in for the school profile's labels (sabha_core/profiles.py). */
export const mockLabels: Labels = {
  person: "Teacher",
  person_plural: "Teachers",
  recording: "Lesson",
  recording_plural: "Lessons",
  unit: "Campus and section",
  manager: "Principal or coordinator",
};

/**
 * Role labels for the transcript and timeline. The labels dictionary has no word yet for the people who are not
 * analysed (see the P6.5 demo), so "Students" stands in for whatever key that decision adds.
 */
export const mockRoles: RoleLabels = {
  teacher: { label: mockLabels.person, analysed: true },
  students: { label: "Students" },
};

const TARGET_DURATION_MS = 52 * 60_000 + 14_000;
const SEED = 2;

/** Index-based utterance id, as the analysis stage writes them today ("u0042"). */
export const utteranceId = (index: number) => `u${String(index).padStart(4, "0")}`;

/** Gaps between turns longer than this count as silence the VAD removed (less padding at each edge). */
const MIN_REMOVED_GAP_MS = 2_000;
const VAD_PAD_MS = 250;

/** Silence a VAD would cut: the lead-in, the tail and every long gap between turns, on the original timeline. */
export function removedSilence(utterances: readonly Utterance[], durationMs: number): TimeRange[] {
  const ranges: TimeRange[] = [];
  let previousEnd = 0;
  for (const u of [...utterances, { start_ms: durationMs, end_ms: durationMs }]) {
    const gap = u.start_ms - previousEnd;
    if (gap >= MIN_REMOVED_GAP_MS) {
      const start = previousEnd === 0 ? 0 : previousEnd + VAD_PAD_MS;
      const end = u.start_ms === durationMs ? durationMs : u.start_ms - VAD_PAD_MS;
      if (end > start) ranges.push({ start_ms: start, end_ms: end });
    }
    previousEnd = Math.max(previousEnd, u.end_ms);
  }
  return ranges;
}

export interface MockLesson {
  transcript: Transcript;
  recording: ReportRecording;
  labels: Labels;
  roles: RoleLabels;
}

/** A 52-minute Hinglish photosynthesis lesson (P6.5 mock transcript, seed 2) and its recording details. */
export function mockLesson(): MockLesson {
  const transcript = generateMockTranscript({ durationMs: TARGET_DURATION_MS - 30_000, seed: SEED, topic: 0 });
  const last = transcript.utterances[transcript.utterances.length - 1] as Utterance;
  const durationMs = Math.max(TARGET_DURATION_MS, last.end_ms + 1_000);
  const silence = removedSilence(transcript.utterances, durationMs);
  const silentMs = silence.reduce((sum, r) => sum + r.end_ms - r.start_ms, 0);
  return {
    transcript,
    labels: mockLabels,
    roles: mockRoles,
    recording: {
      id: "rec_demo_0001",
      title: "Class 8 Science: Photosynthesis",
      type_label: "Teaching",
      person: { id: "per_demo_0001", name: "Anjali Sharma", unit: "Main campus" },
      recorded_at: "2026-10-13T04:35:00Z", // 10:05 am IST
      duration_ms: durationMs,
      speech_ms: durationMs - silentMs,
      languages: ["Hindi", "English"],
      removed_silence: silence,
    },
  };
}

// ---------------------------------------------------------------------------------------------------------------
// Finding quotes in the transcript.

interface Found {
  index: number;
  utterance: Utterance;
}

function find(
  utterances: readonly Utterance[],
  test: (u: Utterance, i: number) => boolean,
  options: { after?: number; last?: boolean } = {},
): Found {
  const after = options.after ?? -1;
  const indexes = utterances.map((_, i) => i).filter((i) => i > after);
  if (options.last) indexes.reverse();
  for (const i of indexes) {
    const u = utterances[i] as Utterance;
    if (test(u, i)) return { index: i, utterance: u };
  }
  throw new Error("mock report: no utterance matches");
}

const indexAfter = (utterances: readonly Utterance[], ms: number) =>
  Math.max(-1, utterances.findIndex((u) => u.start_ms >= ms) - 1);

/** A quote of the whole utterance, or of the part matching `part`. */
function quote(found: Found, part?: RegExp): EvidenceQuote {
  const text = found.utterance.text;
  const match = part ? part.exec(text) : null;
  return {
    quote: match ? match[0] : text,
    utterance_id: utteranceId(found.index),
    start_ms: found.utterance.start_ms,
    end_ms: found.utterance.end_ms,
  };
}

const teacher = (pattern: RegExp) => (u: Utterance) => u.role === "teacher" && pattern.test(u.text);

// ---------------------------------------------------------------------------------------------------------------
// Metrics, counted from the transcript.

const OPEN_QUESTION = /\b(why|how|explain|kyun|kaise)\b/i;
const isQuestion = (u: Utterance) => u.text.includes("?");

/** The longest stretch of consecutive teacher turns with no student turn in between. */
function longestTeacherStretch(utterances: readonly Utterance[]): TimeRange {
  let best: TimeRange = { start_ms: 0, end_ms: 0 };
  let start: number | null = null;
  for (const u of utterances) {
    if (u.role === "teacher") {
      start ??= u.start_ms;
      if (u.end_ms - start > best.end_ms - best.start_ms) best = { start_ms: start, end_ms: u.end_ms };
    } else {
      start = null;
    }
  }
  return best;
}

function mockMetrics(utterances: readonly Utterance[], labels: Labels, roles: RoleLabels, withMedian: boolean) {
  const person = labels.person.toLowerCase();
  const group = (roles.students?.label ?? "students").toLowerCase();
  let teacherMs = 0;
  let allMs = 0;
  let teacherWords = 0;
  for (const u of utterances) {
    const ms = u.end_ms - u.start_ms;
    allMs += ms;
    if (u.role === "teacher") {
      teacherMs += ms;
      teacherWords += u.text.split(/\s+/).length;
    }
  }
  const teacherQuestions = utterances.filter((u) => u.role === "teacher" && isQuestion(u));
  const open = teacherQuestions.filter((u) => OPEN_QUESTION.test(u.text)).length;
  const studentQuestions = utterances.filter((u) => u.role === "students" && isQuestion(u)).length;
  const stretch = longestTeacherStretch(utterances);
  const groupShare = allMs > 0 ? (allMs - teacherMs) / allMs : null;

  const metrics: Metric[] = [
    {
      key: "student_talk_share",
      name: `${roles.students?.label ?? "Students"} talk time`,
      value: groupShare === null ? null : Math.round(groupShare * 100) / 100,
      unit: "ratio",
      definition: `Share of all speech time spoken by the ${group}, from the speaker-labelled transcript. Silence is not counted.`,
      median: withMedian ? { scope: "School", value: 0.24 } : null,
    },
    {
      key: "teacher_question_count",
      name: `Questions asked by ${person}`,
      value: teacherQuestions.length,
      unit: "count",
      definition: `Turns by the ${person} that contain a question. Open questions ask why or how (also kyun, kaise); the rest are recall.`,
      detail: `${open} open, ${teacherQuestions.length - open} recall`,
    },
    {
      key: "student_question_count",
      name: `Questions from ${group}`,
      value: studentQuestions,
      unit: "count",
      definition: `Turns by the ${group} that contain a question.`,
    },
    {
      key: "words_per_minute",
      name: "Speaking pace",
      value: teacherMs > 0 ? Math.round(teacherWords / (teacherMs / 60_000)) : null,
      unit: "wpm",
      definition: `Words the ${person} said per minute of their own speech time.`,
    },
    {
      key: "longest_monologue_ms",
      name: "Longest uninterrupted talk",
      value: stretch.end_ms - stretch.start_ms,
      unit: "ms",
      definition: `The longest stretch of ${person} turns with no ${group} turn in between, pauses included.`,
      range: stretch,
    },
  ];
  return { metrics, stretch };
}

// ---------------------------------------------------------------------------------------------------------------
// The analysis.

const WEIGHTS: Record<string, number> = {
  concept_clarity: 0.25,
  use_of_examples: 0.15,
  checks_for_understanding: 0.2,
  questioning_quality: 0.15,
  pacing: 0.1,
  recap_and_closure: 0.15,
};

/** P5.7's rule: weighted mean of verified dimensions, 1 decimal; null under 60% of the weight verified. */
export function overallScore(dimensions: readonly Dimension[]): number | null {
  const verified = dimensions.filter((d): d is VerifiedDimension => d.verified === true);
  const weight = verified.reduce((sum, d) => sum + d.weight, 0);
  const total = dimensions.reduce((sum, d) => sum + d.weight, 0);
  if (total <= 0 || weight / total < 0.6) return null;
  const mean = verified.reduce((sum, d) => sum + d.score * d.weight, 0) / weight;
  return Math.round(mean * 10) / 10;
}

export type MockReportVariant = "completed" | "no-comparison" | "partial";

/** A full analysis of `mockLesson()`. "partial" leaves two dimensions unverified. */
export function mockReport(lesson: MockLesson, variant: MockReportVariant = "completed"): AnalysisReport {
  const u = lesson.transcript.utterances;
  const { labels, roles } = lesson;
  const recording = labels.recording.toLowerCase();
  const durationMs = lesson.recording.duration_ms;
  const { metrics } = mockMetrics(u, labels, roles, variant !== "no-comparison");

  // Concept clarity: the light reaction, then the Calvin cycle.
  const light = find(u, teacher(/^So the light reaction gives us/));
  const calvin = find(u, teacher(/^Dark reaction ko Calvin cycle/), { after: light.index });
  // Use of examples: the kitchen analogy and the equation on the board.
  const kitchen = find(u, teacher(/^Ek analogy socho/));
  const board = find(u, teacher(/^Board pe dekho/));
  // Checks for understanding: a chorus check that moves straight to the worksheet, around 20 minutes in.
  const chorus = find(u, teacher(/^Sab samajh aaya\?/), { after: indexAfter(u, 18 * 60_000) });
  const doubt = find(u, teacher(/^Theek hai\? Koi doubt\?/), { after: chorus.index });
  const checks = u.filter(teacher(/^(Sab samajh aaya|Theek hai\? Koi doubt|Clear hai sabko)/)).length;
  // Questioning: a recall question to one student and an open "why" question.
  const recall = find(u, (x, i) => teacher(/^[A-Z][a-z]+, glucose banane/)(x) && u[i + 1]?.role === "students", {
    after: indexAfter(u, 12 * 60_000),
  });
  const why = find(u, teacher(/^Why do leaves look green\?/), { after: recall.index });
  // Pacing: the worksheet is set in the first minutes and again near the end.
  const early = find(u, teacher(/^Take out page 44/));
  const late = find(u, teacher(/^Take out page 44/), { after: indexAfter(u, 40 * 60_000) });
  // Recap and closure: the last two teacher turns.
  const lastTurn = find(u, (x) => x.role === "teacher", { last: true });
  const beforeLast = find(u, (x, i) => x.role === "teacher" && i < lastTurn.index, { last: true });

  const at = (f: Found) => formatClock(f.utterance.start_ms);
  const minutes = Math.round(durationMs / 60_000);

  const dimensions: VerifiedDimension[] = [
    {
      key: "concept_clarity",
      name: "Concept clarity",
      weight: WEIGHTS.concept_clarity as number,
      verified: true,
      score: 4,
      rationale: `States what the light reaction produces and where the Calvin cycle happens, and keeps the two stages in order. Key terms such as stroma and thylakoid are used without being defined first.`,
      evidence: [quote(light), quote(calvin)],
      suggestion: `When stroma comes up at ${at(calvin)}, define it in one sentence before going on.`,
    },
    {
      key: "use_of_examples",
      name: "Use of examples",
      weight: WEIGHTS.use_of_examples as number,
      verified: true,
      score: 4,
      rationale: `The kitchen analogy and the worked equation on the board both match the concept and are linked back to it.`,
      evidence: [quote(kitchen, /^Ek analogy socho: leaf ek kitchen hai/), quote(board)],
      suggestion: `Ask the class to extend the kitchen analogy themselves: what would the stomata be?`,
    },
    {
      key: "checks_for_understanding",
      name: "Checks for understanding",
      weight: WEIGHTS.checks_for_understanding as number,
      verified: true,
      score: 2,
      rationale: `Understanding was checked ${checks} times in ${minutes} minutes, each time with a yes or no question answered in chorus. At ${at(chorus)} the class moved to the worksheet straight after the chorus reply, without anyone being asked to explain.`,
      evidence: [quote(chorus), quote(doubt)],
      suggestion: `At ${at(chorus)}, replace the yes or no check with a question to three different students before starting the worksheet.`,
    },
    {
      key: "questioning_quality",
      name: "Questioning quality",
      weight: WEIGHTS.questioning_quality as number,
      verified: true,
      score: 3,
      rationale: `Most questions are recall with one-word answers. The why-question about green leaves asks for a reason, but the first answer is accepted without a follow-up.`,
      evidence: [quote(recall), quote(why, /^Why do leaves look green\?/)],
      suggestion: `After the first answer to a why-question, ask another student whether they agree and why.`,
    },
    {
      key: "pacing",
      name: "Pacing",
      weight: WEIGHTS.pacing as number,
      verified: true,
      score: 3,
      rationale: `Explanation, questions and practice are mixed throughout, with pauses for questions, but the worksheet is set at ${at(early)} and again at ${at(late)}, so practice never gets a block of its own.`,
      evidence: [quote(early, /^Take out page 44\./), quote(late)],
      suggestion: `Finish the explanation first, then give the worksheet one protected block, for example from ${at(late)}.`,
    },
    {
      key: "recap_and_closure",
      name: "Recap and closure",
      weight: WEIGHTS.recap_and_closure as number,
      verified: true,
      score: 2,
      rationale: `The ${recording} ends in the middle of the explanation. There is no summary of the two stages and no exit question.`,
      evidence: [quote(beforeLast), quote(lastTurn)],
      suggestion: `Keep the last four minutes for two students to explain the light and dark reactions in one sentence each.`,
    },
  ];

  const all: Dimension[] =
    variant === "partial"
      ? dimensions.map((d): Dimension => {
          if (d.key !== "pacing" && d.key !== "recap_and_closure") return d;
          const hidden: UnverifiedDimension = { key: d.key, name: d.name, weight: d.weight, verified: false };
          return hidden;
        })
      : dimensions;

  const suggestions: Suggestion[] = [
    {
      text: `Replace “Sab samajh aaya?” with a question to three students before starting the worksheet.`,
      utterance_id: utteranceId(chorus.index),
      start_ms: chorus.utterance.start_ms,
    },
    {
      text: `After the first answer to “Why do leaves look green?”, ask another student whether they agree, and why.`,
      utterance_id: utteranceId(why.index),
      start_ms: why.utterance.start_ms,
    },
    {
      text: `Keep the last four minutes for two students to explain both stages in one sentence each.`,
      utterance_id: utteranceId(beforeLast.index),
      start_ms: beforeLast.utterance.start_ms,
    },
  ];
  const share = metrics[0]?.value;

  return {
    status: variant === "partial" ? "partial" : "completed",
    reasons:
      variant === "partial"
        ? [
            {
              code: "dimension_unverified",
              message: "Quotes for Pacing and Recap and closure could not be found in the transcript after one retry.",
            },
          ]
        : [],
    analysis_id: "ana_demo_0001",
    recording_id: lesson.recording.id,
    created_at: "2026-10-13T05:41:00Z",
    rubric: { id: "teaching.school.v0.1", version: "0.1", name: "Teaching" },
    model: { ids: ["mock-judge-2026-10"], prompt_hash: "demo" },
    overall: overallScore(all),
    comparison: variant === "no-comparison" ? null : { scope: "school", median: 3.5 },
    person_history: variant === "no-comparison" ? null : { count: 5, min: 2.8, max: 3.4 },
    dimensions: all,
    metrics,
    summary:
      `A clearly ordered ${recording} with a strong kitchen analogy for photosynthesis. ` +
      `The ${roles.students?.label.toLowerCase() ?? "students"} spoke for ${share == null ? "little" : `${Math.round(share * 100)}%`} of the speech time, ` +
      `understanding was checked only with yes or no questions, and the ${recording} ended without a recap.`,
    strengths: ["Concepts explained in order", "Analogy linked back to the concept"],
    gaps: ["Checks for understanding are yes or no only", "No recap at the end"],
    suggestions,
    phases: [
      { name: "Introduction", start_ms: 0, end_ms: 6 * 60_000 },
      { name: "Explanation", start_ms: 6 * 60_000, end_ms: 24 * 60_000 },
      { name: "Guided practice", start_ms: 24 * 60_000, end_ms: 41 * 60_000 },
      { name: "Closing", start_ms: 41 * 60_000, end_ms: durationMs },
    ],
  };
}

export function mockProcessing(lesson: MockLesson): AnalysisProcessing {
  return {
    status: "processing",
    reasons: [],
    recording_id: lesson.recording.id,
    stage: "transcribing",
    progress: 0.62,
    updated_at: "2026-10-13T05:20:00Z",
  };
}

export function mockFailed(lesson: MockLesson): AnalysisFailed {
  return {
    status: "failed",
    reasons: [
      { code: "audio_unreadable", message: "The audio file could not be decoded. It may be damaged or empty." },
    ],
    recording_id: lesson.recording.id,
    reference: "run_demo_7f3a",
  };
}

export function mockNeedsReview(lesson: MockLesson): AnalysisNeedsReview {
  return {
    status: "needs_review",
    reasons: [
      {
        code: "low_verification",
        message:
          "Fewer than 60% of the rubric weight could be checked against the transcript, so no overall score was given.",
      },
    ],
    recording_id: lesson.recording.id,
  };
}
