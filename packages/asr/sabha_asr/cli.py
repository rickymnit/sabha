"""`sabha-asr-transcribe FILE.wav`: transcribe one local WAV with the configured provider (a P3.1 smoke test).

For checking a provider by hand, not for the pipeline. Reads ASR_* and the provider's settings from the environment
(.env). The file must be 16 kHz mono 16-bit PCM WAV; convert others with
`ffmpeg -i in.m4a -ar 16000 -ac 1 -c:a pcm_s16le out.wav`. There is no VAD here, so long files are cut with the
in-speech overlap rule of sabha_asr.chunking. Prints the provider, model, word timing, real-time factor and
fallback reason to stderr, and the words as JSON lines ({text, start_ms, end_ms, confidence}) to stdout.

Use only recordings you may send to the provider: real recordings need consent and the provider's data terms
confirmed first (ADR 0006).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import wave
from collections.abc import Sequence

from sabha_asr.chunking import merge_chunk_words, plan_chunks
from sabha_asr.provider import AudioChunk
from sabha_asr.registry import build_transcriber
from sabha_core.settings import load_settings

SAMPLE_RATE = 16_000
_BYTES_PER_MS = SAMPLE_RATE * 2 // 1000  # 16-bit mono


def _read_pcm(path: str) -> bytes:
    with wave.open(path, "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise SystemExit(f"{path}: need 16 kHz mono 16-bit PCM WAV; convert it with ffmpeg (see --help)")
        return wav.readframes(wav.getnframes())


def _wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return buffer.getvalue()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wav", help="16 kHz mono 16-bit PCM WAV file")
    args = parser.parse_args(argv)

    transcriber = build_transcriber(load_settings())
    pcm = _read_pcm(args.wav)
    length_ms = len(pcm) // _BYTES_PER_MS
    max_chunk_ms = min(p.max_chunk_ms for p in (transcriber.primary, *transcriber.fallbacks))
    chunks = plan_chunks(length_ms, [], max_chunk_ms=max_chunk_ms - max_chunk_ms % 2)
    audio = [
        AudioChunk(f"chunk-{c.index}", _wav(pcm[c.start_ms * _BYTES_PER_MS : c.end_ms * _BYTES_PER_MS]), c.duration_ms)
        for c in chunks
    ]
    outcome = transcriber.transcribe(audio)
    words = merge_chunk_words((c, r.words) for c, r in zip(chunks, outcome.results, strict=True))
    print(
        f"provider={outcome.provider} model={outcome.model_id} word_timing={outcome.word_timing} "
        f"audio_ms={outcome.audio_ms} rtf={outcome.real_time_factor:.3f} fallback={outcome.fallback_reason}",
        file=sys.stderr,
    )
    for word in words:
        print(json.dumps(word.to_record(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
