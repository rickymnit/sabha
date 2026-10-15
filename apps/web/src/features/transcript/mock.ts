// Mock transcript@v1 data for the demo page and tests, until the transcript API (P3.7) exists.
// Deterministic for a given seed. Hinglish classroom speech; every name is fictional. Roles follow the teaching
// rubric (rubrics/teaching.school.v0.1.yaml: teacher, students); students are a group, never identified.

import type { LowConfidenceSpan, Transcript, Utterance } from "./types";

export interface MockTranscriptOptions {
  /** Generate until the last line ends at or after this time. */
  durationMs?: number;
  /** Generate exactly this many lines (wins over durationMs). */
  lines?: number;
  seed?: number;
  /**
   * Keep to one subject for the whole recording: 0 photosynthesis, 1 fractions, 2 water cycle, 3 tenses. By default
   * the subject is picked from the seed and changes every 40 minutes.
   */
  topic?: number;
}

/** Small, fast, seedable PRNG (mulberry32). */
function random(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Topic {
  explain: string[];
  /** A question and a typical answer to it. */
  qa: [string, string][];
}

const TOPICS: Topic[] = [
  {
    explain: [
      "So the light reaction gives us two things, ATP and NADPH, and oxygen goes out through the stomata.",
      "This oxygen is what we breathe. Isliye plants itne important hain.",
      "Chlorophyll green light ko reflect karta hai, baaki colours absorb karta hai, that is why leaves look green.",
      "Dark reaction ko Calvin cycle bhi kehte hain, aur ye stroma mein hota hai, thylakoid mein nahi.",
      "Carbon dioxide plus water, sunlight ki energy se, glucose aur oxygen ban jaate hain.",
      "Ek analogy socho: leaf ek kitchen hai, sunlight gas stove hai, aur glucose hamara khana hai.",
      "Board pe dekho, maine equation likha hai. Six CO2 plus six H2O gives C6H12O6 plus six O2.",
      "Stomata din mein khulte hain aur raat ko zyada tar band rehte hain, to save water.",
    ],
    qa: [
      ["What comes out of the light reaction?", "Oxygen, ma'am. Aur ATP bhi."],
      ["Batao, Calvin cycle kahan hota hai?", "Stroma mein, ma'am."],
      ["Why do leaves look green? Koi bhi bata sakta hai.", "Because chlorophyll green reflect karta hai."],
      ["Glucose banane ke liye kaun si do cheezein chahiye?", "Carbon dioxide and water."],
    ],
  },
  {
    explain: [
      "Fractions add karne se pehle denominator same karna padta hai, warna answer galat aayega.",
      "Three by four plus one by eight. LCM of four and eight is eight, toh three by four becomes six by eight.",
      "Ek pizza socho, aath slices mein cut kiya. Six slices plus one slice, kitne hue? Seven by eight.",
      "Improper fraction ko mixed number mein convert karna simple hai, divide karo aur remainder upar likho.",
      "Numerator upar wala number hai, denominator neeche wala. Ye confusion mat karna exam mein.",
      "Equivalent fractions same value dikhate hain, jaise one by two aur two by four.",
    ],
    qa: [
      ["Two by three plus one by six, kitna hoga?", "Five by six, ma'am."],
      ["Denominator kaun sa hota hai, upar wala ya neeche wala?", "Neeche wala."],
      ["Nine by four ko mixed number mein likho, quickly.", "Two and one by four."],
      ["Pehla step kya hai jab denominators alag hon?", "Ma'am, LCM pehle nikaalna hai."],
    ],
  },
  {
    explain: [
      "Water cycle mein chaar steps hain: evaporation, condensation, precipitation aur collection.",
      "Sooraj ki garmi se samudra ka paani bhaap ban ke upar jaata hai, that is evaporation.",
      "Upar thanda hota hai, toh vapour chhote droplets ban jaata hai, aur clouds bante hain.",
      "Jab droplets heavy ho jaate hain, toh baarish hoti hai. Mountains pe ye snow bhi ho sakta hai.",
      "Plants bhi paani chhodte hain leaves se, usko transpiration kehte hain. Ye bhi cycle ka part hai.",
    ],
    qa: [
      ["Clouds kaise bante hain?", "Condensation se, ma'am."],
      ["Evaporation ke liye energy kahan se aati hai?", "Sun se."],
      ["Transpiration kya hai, ek line mein batao.", "Plants leaves se paani release karte hain."],
    ],
  },
  {
    explain: [
      "Present perfect tense mein has ya have plus third form use hota hai. I have finished my homework.",
      "Simple past mein time fixed hota hai, jaise yesterday, last week. I finished it yesterday.",
      "Dhyaan do, since ke saath point of time aata hai aur for ke saath period of time.",
      "She has lived in Pune for five years. Yahan for kyun use kiya? Kyunki five years ek period hai.",
    ],
    qa: [
      ["Since ya for: I have known him blank twenty twenty.", "Since, ma'am."],
      ["Third form of go kya hai?", "Went? Nahi nahi, gone."],
      ["Is sentence ka tense batao: they have reached school.", "Present perfect."],
    ],
  },
];

const NAMES = ["Aarav", "Diya", "Kabir", "Meera", "Ishaan", "Riya", "Vivaan", "Anaya", "Arjun", "Sara"];

const CHECKS = [
  "Sab samajh aaya? Okay, good, let us move to the worksheet.",
  "Theek hai? Koi doubt?",
  "Clear hai sabko? Haath upar karo jinko doubt hai.",
];
const PRAISE = ["Bilkul sahi!", "Good, almost there.", "Very good. Sab log clap karo.", "Hmm, close. Try again."];
const MANAGE = [
  "Chalo, sab log page 44 kholo.",
  "Take out page 44. Do questions 1 to 10 in your notebook, you have fifteen minutes.",
  "Back row, please, thoda dhyaan do.",
  "Notebook band karo, board pe dekho.",
  "Two minutes aur, phir hum check karenge.",
];
const CHORUS = ["Yes ma'am.", "Haan ma'am.", "No ma'am.", "Ma'am, ek baar phir se bataiye?", "Ma'am, page number?"];

/** A mock transcript@v1. Defaults: a 3-hour classroom recording, seed 1. */
export function generateMockTranscript(options: MockTranscriptOptions = {}): Transcript {
  const { lines, seed = 1 } = options;
  const durationMs = lines === undefined ? (options.durationMs ?? 3 * 60 * 60 * 1000) : Infinity;
  const maxLines = lines ?? Infinity;
  const rand = random(seed);
  const pick = <T>(items: readonly T[]): T => items[Math.floor(rand() * items.length)] as T;
  let lastText = "";
  /** Like pick, but never the line just said. */
  const say = (items: readonly string[]): string => {
    let text = pick(items);
    for (let tries = 0; text === lastText && tries < 4; tries++) text = pick(items);
    return text;
  };

  const utterances: Utterance[] = [];
  let clock = 2_000 + Math.floor(rand() * 4_000);
  // Always draw the random subject, so the rest of the sequence (and the default output for a seed) is unchanged.
  const randomTopic = Math.floor(rand() * TOPICS.length);
  let topicIndex = options.topic === undefined ? randomTopic : options.topic % TOPICS.length;
  let topicChangeAt = options.topic === undefined ? 40 * 60_000 : Infinity;

  const push = (role: "teacher" | "students", text: string) => {
    const words = text.split(/\s+/).length;
    const perWord = role === "teacher" ? 360 + rand() * 80 : 330 + rand() * 60;
    const length = Math.round(words * perWord + 300 + rand() * 500);
    const start = clock;
    const end = start + length;
    // Students are further from the microphone, so their speech is less certain more often.
    const allSpans = rand() < (role === "teacher" ? 0.12 : 0.25) ? lowConfidence(text, rand) : [];
    const base = role === "teacher" ? 0.88 : 0.76;
    lastText = text;
    utterances.push({
      role,
      speaker_label: role === "teacher" ? "SPEAKER_00" : `SPEAKER_0${1 + Math.floor(rand() * 5)}`,
      start_ms: start,
      end_ms: end,
      text,
      avg_confidence: Math.round((base + rand() * 0.1 - (allSpans.length ? 0.08 : 0)) * 100) / 100,
      low_confidence_spans: allSpans,
    });
    // Usually a short pause between turns; now and then a long one (writing work, settling down).
    const gap = rand() < 0.04 ? 8_000 + rand() * 40_000 : 250 + rand() * 1_300;
    clock = end + Math.round(gap);
  };

  const done = () => utterances.length >= maxLines || clock >= durationMs;

  while (!done()) {
    if (clock >= topicChangeAt) {
      topicIndex = (topicIndex + 1) % TOPICS.length;
      topicChangeAt += 40 * 60_000;
    }
    const topic = TOPICS[topicIndex] as Topic;
    const roll = rand();
    if (roll < 0.5) {
      push("teacher", say(topic.explain));
    } else if (roll < 0.75) {
      const [question, answer] = pick(topic.qa);
      push(
        "teacher",
        rand() < 0.4 ? `${pick(NAMES)}, ${question.charAt(0).toLowerCase()}${question.slice(1)}` : question,
      );
      if (!done()) push("students", answer);
      if (!done() && rand() < 0.6) push("teacher", say(PRAISE));
    } else if (roll < 0.87) {
      push("teacher", say(CHECKS));
      if (!done()) push("students", say(CHORUS));
    } else {
      push("teacher", say(MANAGE));
    }
  }
  const kept = utterances.slice(0, maxLines);
  const wordCount = kept.reduce((sum, u) => sum + u.text.split(/\s+/).length, 0);
  return { version: "transcript@v1", timeline: "original", asr_model: "mock", word_count: wordCount, utterances: kept };
}

/** Marks one word (sometimes two) as low confidence. Offsets are code points, as the API sends them. */
function lowConfidence(text: string, rand: () => number): LowConfidenceSpan[] {
  const chars = Array.from(text);
  const words: [number, number][] = [];
  let start = -1;
  chars.forEach((char, i) => {
    const isWord = /[\p{L}\p{N}']/u.test(char);
    if (isWord && start < 0) start = i;
    if (!isWord && start >= 0) {
      words.push([start, i]);
      start = -1;
    }
  });
  if (start >= 0) words.push([start, chars.length]);
  const long = words.filter(([s, e]) => e - s >= 4);
  if (long.length === 0) return [];
  const first = Math.floor(rand() * long.length);
  const [s] = long[first] as [number, number];
  const last = long[Math.min(long.length - 1, first + (rand() < 0.3 ? 1 : 0))] as [number, number];
  return [[s, last[1]]];
}
