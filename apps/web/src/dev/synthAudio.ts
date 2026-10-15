// Dev only: builds a WAV in the browser that follows a mock transcript, so the demo has real audio to seek in.
// Each line is a soft tone (low for the analysed role, higher for others) pulsing like syllables; gaps are silent.
// 8-bit mono keeps a 3-hour file near 32 MB at 3 kHz, the lowest rate Chromium plays.

import type { Utterance } from "../features/transcript";

export interface SynthOptions {
  durationMs: number;
  /** Samples per second. 3000 for long files; 16000 sounds nicer for short ones. */
  sampleRate?: number;
  /** Roles drawn with the lower tone. */
  lowToneRoles?: readonly string[];
}

const TABLE_SIZE = 1024;
const SINE = Float32Array.from({ length: TABLE_SIZE }, (_, i) => Math.sin((2 * Math.PI * i) / TABLE_SIZE));

export function synthesizeWav(utterances: readonly Utterance[], options: SynthOptions): Blob {
  const { durationMs, sampleRate = 3000, lowToneRoles = ["teacher"] } = options;
  const samples = Math.ceil((durationMs / 1000) * sampleRate);
  const header = 44;
  const buffer = new Uint8Array(header + samples);
  const view = new DataView(buffer.buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) buffer[offset + i] = text.charCodeAt(i);
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate, true); // byte rate: 1 byte per sample
  view.setUint16(32, 1, true); // block align
  view.setUint16(34, 8, true); // bits per sample
  ascii(36, "data");
  view.setUint32(40, samples, true);

  buffer.fill(128, header); // 8-bit PCM silence
  const low = new Set(lowToneRoles);
  for (const u of utterances) {
    const from = Math.floor((u.start_ms / 1000) * sampleRate);
    const to = Math.min(samples, Math.floor((u.end_ms / 1000) * sampleRate));
    const step = ((low.has(u.role) ? 196 : 392) / sampleRate) * TABLE_SIZE;
    const pulse = (4 / sampleRate) * TABLE_SIZE; // about four "syllables" a second
    let phase = 0;
    let pulsePhase = 0;
    for (let i = from; i < to; i++) {
      const envelope = 0.35 + 0.65 * Math.abs(SINE[pulsePhase & (TABLE_SIZE - 1)] as number);
      buffer[header + i] = 128 + Math.round(40 * envelope * (SINE[phase & (TABLE_SIZE - 1)] as number));
      phase = (phase + step) % TABLE_SIZE;
      pulsePhase = (pulsePhase + pulse) % TABLE_SIZE;
    }
  }
  return new Blob([buffer], { type: "audio/wav" });
}
