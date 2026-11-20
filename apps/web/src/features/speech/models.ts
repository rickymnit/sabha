// Speech-to-text model helpers and the speech choices' values (ADR 0012, 0014, 0015, 0017, 0018).

import type { SpeechModel } from "../../api/types";

export const MODEL_KEY = "sabha.upload.asr_model";

/** The speech-to-text model last chosen on this device, if it is still offered and set up; else the default. */
export function rememberedModel(models: readonly SpeechModel[]): string {
  let last: string | null = null;
  try {
    last = localStorage.getItem(MODEL_KEY);
  } catch {
    // Storage blocked: the default.
  }
  const usable = models.filter((m) => m.available);
  return (usable.find((m) => m.id === last) ?? usable.find((m) => m.default) ?? usable[0])?.id ?? "";
}

export function rememberModel(id: string) {
  try {
    localStorage.setItem(MODEL_KEY, id);
  } catch {
    // Storage blocked: nothing to remember, nothing lost.
  }
}

/** "Sarvam Saaras v4 · ₹29.40/hour", short enough for the box; "(not set up)" on the ones that cannot be chosen. */
export function modelLabel(m: SpeechModel): string {
  const price = m.inr_per_hour === null ? "no per-minute charge" : `₹${m.inr_per_hour.toFixed(2)}/hour`;
  return `${m.name} · ${price}${m.available ? "" : " (not set up)"}`;
}

export interface SpeechValue {
  /** "provider:model" from GET /v1/speech-models; "" until the list has loaded. */
  asrModel: string;
  /** "auto" or "2" to "10". */
  speakers: string;
  speakerModel: "pyannote" | "gemini";
  /** Support calls: a colleague helped (three speakers). */
  transferred: boolean;
}

/** The request fields for these choices (the API's names), leaving out what is the default. */
export function speechFields(value: SpeechValue, support: boolean, chooseModel: boolean) {
  const helped = support && value.transferred;
  const count = helped ? 3 : value.speakers === "auto" ? null : Number(value.speakers);
  return {
    ...(chooseModel && value.asrModel ? { asr_model: value.asrModel } : {}),
    ...(count !== null ? { speaker_count: count } : {}),
    ...(value.speakerModel !== "pyannote" ? { speaker_model: value.speakerModel } : {}),
    ...(support ? { transferred: helped } : {}),
  };
}
