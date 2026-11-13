"""Compare speech-to-text models on calls Sabha has already transcribed with Sarvam (ADR 0012).

    uv run python eval/asr_compare.py --tenant demo-company --models openai,qwen,aws,whisper:small [--latest 5]
    uv run python eval/asr_compare.py --tenant demo-company --models openai:gpt-4o-mini-transcribe --recordings ID,ID

Models are "provider[:model]" (sabha_asr.registry; keys from .env). For each recording (the latest N completed audio
recordings, or the ids given) the script:

1. reads the transcribe stage's inputs from storage (compact.wav, segments@v1.json, diarization@v1.json) and plans
   the SAME chunks the stage plans: at most 29.5 s, cut at pauses and at every change of speaker;
2. takes Sarvam's words from the recording's own asr@v1.json, so Sarvam is not asked (or paid) again;
3. sends the same chunks to every model and merges each model's words with the pipeline's owned-region rule.
   Answers are cached under the output folder (cache/), so running again never pays twice for the same audio.

The report goes to eval/reports/asr-compare-<date>/ (index.html, summary.json; git-ignored: it holds transcripts).
Per model: audio minutes sent, the published price and its source (sabha_asr.pricing), the cost of these calls and
per hour of audio (rupees for a dollar price only with USD_INR_RATE), processing time and real-time factor, and the
DIFFERENCE FROM SARVAM: (substitutions + deletions + insertions) / Sarvam's words, chunk by chunk, after the
textnorm.py normalisation, both as written and transliterated (so "अच्छा" and "achha" count as the same word).
Then every call, chunk by chunk, with the texts side by side, words that differ from Sarvam highlighted, and the
time on the original recording.

The difference is NOT accuracy (golden rule 6): no human transcript is involved, and Sarvam makes mistakes too. It
shows where the models disagree; listen to those moments to decide which is right. Word error rate against
human-checked transcripts comes only from eval/wer.py on the gold set.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import sys
import tempfile
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from textnorm import tokens
from wer import Counts, align, corpus_counts

from sabha_asr.chunking import Chunk, compact_joins, merge_chunk_words, plan_chunks, speaker_cuts
from sabha_asr.pricing import price_for
from sabha_asr.provider import AsrProvider, ChunkResult, ProviderError
from sabha_asr.registry import build_provider, model_id_for, parse_spec
from sabha_asr.words import Turn, Word
from sabha_core.models import Recording
from sabha_core.repo import SyncTenantRepo
from sabha_core.settings import Settings, load_settings
from sabha_core.state import RecordingStatus
from sabha_core.storage import artefact_prefix, run_version
from sabha_core.timemap import SegmentMap

EVAL_DIR = Path(__file__).resolve().parent
SARVAM = "sarvam"
MAX_CHUNK_MS = 29_500  # the transcribe stage's plan with Sarvam (every provider here accepts it)
BATCH = 10
MAX_RUNS = 9  # re-analysis runs to look for (transcribe@v1, v1-run2, ...)


@dataclass
class ModelRun:
    """One model on one recording."""

    words_by_chunk: list[list[Word]] = field(default_factory=list)
    sent_ms: int = 0
    compute_ms: int = 0
    error: str | None = None


@dataclass
class Call:
    recording: Recording
    chunks: list[Chunk]
    segment_map: SegmentMap
    runs: dict[str, ModelRun] = field(default_factory=dict)  # model id -> run; Sarvam's included


# --- Reading what the pipeline saved ---


def _read(s3: Any, bucket: str, key: str) -> bytes:
    try:
        body: bytes = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except s3.exceptions.NoSuchKey as exc:
        raise FileNotFoundError(key) from exc
    return body


def _latest_transcribe(s3: Any, bucket: str, tenant_id: str, recording_id: str, version: str) -> str | None:
    """The newest transcribe run's folder that has asr@v1.json."""
    found = None
    for run in range(1, MAX_RUNS + 1):
        prefix = artefact_prefix(tenant_id, recording_id, "transcribe", run_version(version, run))
        try:
            s3.head_object(Bucket=bucket, Key=prefix + "asr@v1.json")
        except s3.exceptions.ClientError:
            continue
        found = prefix
    return found


def load_call(s3: Any, settings: Settings, recording: Recording, tmp: Path) -> tuple[Call, Path, dict[str, Any]]:
    bucket, tenant = settings.s3_bucket_artefacts, recording.tenant_id
    source = artefact_prefix(tenant, recording.id, "preprocess", settings.artefact_version_preprocess)
    diarized = artefact_prefix(tenant, recording.id, "diarize", settings.artefact_version_diarize)
    transcribed = _latest_transcribe(s3, bucket, tenant, recording.id, settings.artefact_version_transcribe)
    if transcribed is None:
        raise FileNotFoundError("no asr@v1.json")
    segment_map = SegmentMap.from_json(_read(s3, bucket, source + "segments@v1.json"))
    turns = json.loads(_read(s3, bucket, diarized + "diarization@v1.json"))["compact"]
    asr = json.loads(_read(s3, bucket, transcribed + "asr@v1.json"))
    compact = tmp / f"{recording.id}.wav"
    compact.write_bytes(_read(s3, bucket, source + "compact.wav"))
    cuts = speaker_cuts(Turn(t["speaker_label"], t["start_ms"], t["end_ms"]) for t in turns)
    chunks = plan_chunks(segment_map.compact_length_ms, compact_joins(segment_map), max_chunk_ms=MAX_CHUNK_MS,
                         speaker_cuts_ms=cuts.inside, quiet_cuts_ms=cuts.quiet)  # fmt: skip
    return Call(recording, list(chunks), segment_map), compact, asr


def by_chunk(chunks: Sequence[Chunk], words: Sequence[Word]) -> list[list[Word]]:
    """Words (compact timeline) given to the chunk that owns their midpoint, as the pipeline does."""
    out: list[list[Word]] = [[] for _ in chunks]
    index = 0
    for word in sorted(words, key=lambda w: (w.start_ms, w.end_ms)):
        middle = (word.start_ms + word.end_ms) / 2
        while index < len(chunks) - 1 and middle >= chunks[index].owned_end_ms:
            index += 1
        out[index].append(word)
    return out


# --- Asking the models ---


def _cache_file(out: Path, model_id: str, language: str, recording_id: str) -> Path:
    """One cached answer per model, language hint (ASR_LANGUAGE) and recording."""
    folder = re.sub(r"[^A-Za-z0-9._@-]+", "_", f"{model_id}-{language}")
    return out / "cache" / folder / f"{recording_id}.json"


def run_model(provider: AsrProvider, call: Call, compact: Path, out: Path, workers: int, language: str) -> ModelRun:
    from sabha_workers.stages.transcribe import _cut  # the stage's own cutter: same audio bytes per chunk

    plan = [[c.start_ms, c.end_ms, c.owned_start_ms, c.owned_end_ms] for c in call.chunks]
    cache = _cache_file(out, provider.model_id, language, call.recording.id)
    run = ModelRun(sent_ms=sum(c.duration_ms for c in call.chunks))
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved["plan"] == plan:
            cached = [[Word.from_record(w) for w in words] for words in saved["words"]]
            merged = merge_chunk_words(zip(call.chunks, cached, strict=True))
            run.words_by_chunk, run.compute_ms = by_chunk(call.chunks, merged), saved["compute_ms"]
            return run
    audio = [_cut(compact, chunk) for chunk in call.chunks]
    batches = [audio[i : i + BATCH] for i in range(0, len(audio), BATCH)]

    def ask(batch: list[Any]) -> tuple[list[ChunkResult], int]:
        started = time.perf_counter()
        results = provider.transcribe(batch)
        return results, round((time.perf_counter() - started) * 1000)

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            answered = list(pool.map(ask, batches))
    except ProviderError as exc:
        run.error = exc.reason
        return run
    run.compute_ms = sum(ms for _, ms in answered)
    words = [list(r.words) for batch, _ in answered for r in batch]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"model": provider.model_id, "plan": plan, "compute_ms": run.compute_ms,
                                 "words": [[w.to_record() for w in ws] for ws in words]},
                                ensure_ascii=False), encoding="utf-8")  # fmt: skip
    run.words_by_chunk = by_chunk(call.chunks, merge_chunk_words(zip(call.chunks, words, strict=True)))
    return run


# --- Comparing ---


def difference(reference: list[list[Word]], other: list[list[Word]], *, transliterated: bool) -> Counts:
    """Edit distance from Sarvam's words, chunk by chunk (the chunks are the same audio for both)."""
    return corpus_counts(
        align(tokens(" ".join(w.text for w in ref), transliterated=transliterated),
              tokens(" ".join(w.text for w in hyp), transliterated=transliterated), wildcards=frozenset())
        for ref, hyp in zip(reference, other, strict=True)
    )  # fmt: skip


def _key(word: str) -> str:
    return " ".join(tokens(word, transliterated=True))


def marked(reference: Sequence[Word], words: Sequence[Word]) -> str:
    """`words` as HTML, the ones not matching Sarvam's (transliterated, normalised) in <mark>."""
    ref, hyp = [_key(w.text) for w in reference], [_key(w.text) for w in words]
    keep: set[int] = set()
    for block in difflib.SequenceMatcher(a=ref, b=hyp, autojunk=False).get_matching_blocks():
        keep.update(range(block.b, block.b + block.size))
    return " ".join(html.escape(w.text) if i in keep or not hyp[i] else f"<mark>{html.escape(w.text)}</mark>"
                    for i, w in enumerate(words))  # fmt: skip


@dataclass
class ModelSummary:
    model_id: str
    calls: int
    failed: list[str]
    sent_minutes: float
    compute_s: float
    price: str
    price_source: str | None
    cost_inr: float | None
    cost_native: str | None
    inr_per_audio_hour: float | None
    real_time_factor: float | None
    difference_raw: float | None
    difference_translit: float | None


def summarise(model_id: str, calls: Sequence[Call], rate: float | None) -> ModelSummary:
    runs = [(c, c.runs[model_id]) for c in calls if model_id in c.runs]
    done = [(c, r) for c, r in runs if r.error is None]
    sent_ms = sum(r.sent_ms for _, r in done)
    compute_ms = sum(r.compute_ms for _, r in done)
    minutes = sent_ms / 60_000
    price = price_for(model_id)
    native = None if price is None else price.per_minute * minutes
    inr_minute = None if price is None else price.inr_per_minute(rate)
    cost_inr = None if inr_minute is None else inr_minute * minutes
    raw = translit = None
    sarvam = next((m for m in calls[0].runs if m.startswith(SARVAM + "/")), None) if calls else None
    if model_id != sarvam and sarvam is not None:
        pairs = [(c.runs[sarvam].words_by_chunk, r.words_by_chunk) for c, r in done if sarvam in c.runs]
        if pairs:
            raw = corpus_counts(difference(a, b, transliterated=False) for a, b in pairs).wer
            translit = corpus_counts(difference(a, b, transliterated=True) for a, b in pairs).wer
    symbol = {"INR": "₹", "USD": "$"}
    return ModelSummary(
        model_id=model_id, calls=len(done), failed=[f"{c.recording.id}: {r.error}" for c, r in runs if r.error],
        sent_minutes=round(minutes, 2), compute_s=round(compute_ms / 1000, 1),
        price="no per-minute price (own machine)" if model_id.startswith("whisper/") else
        ("not published or not checked" if price is None else f"{symbol[price.currency]}{price.per_minute:g} / min"),
        price_source=price.source if price else None,
        cost_inr=None if cost_inr is None else round(cost_inr, 2),
        cost_native=None if native is None or price is None else f"{symbol[price.currency]}{native:.4f}",
        inr_per_audio_hour=None if inr_minute is None else round(inr_minute * 60, 2),
        real_time_factor=round(compute_ms / sent_ms, 3) if sent_ms and compute_ms else None,
        difference_raw=raw, difference_translit=translit,
    )  # fmt: skip


# --- Report ---

_CSS = """
:root{--ink:#1a1d24;--muted:#5d6472;--line:#e3e6ec;--bg:#f6f7f9;--card:#fff;--mark:#ffe08a;--accent:#3346d3}
@media (prefers-color-scheme:dark){:root{--ink:#e8eaf0;--muted:#a3a9b6;--line:#2c313b;--bg:#14161b;--card:#1c1f26;
--mark:#6b5310;--accent:#8c9bff}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:32px 0 10px}.muted{color:var(--muted)}.card{background:var(--card);border:1px solid
var(--line);border-radius:12px;padding:16px 18px;margin:12px 0;overflow-x:auto}table{border-collapse:collapse;
width:100%}th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line)}
th{font-size:13px;color:var(--muted);font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums;
white-space:nowrap}mark{background:var(--mark);color:inherit;border-radius:3px;padding:0 2px}details{margin:10px 0}
summary{cursor:pointer;font-weight:600;padding:6px 0}.note{border-left:4px solid var(--accent)}td.t{white-space:
nowrap;color:var(--muted);font-variant-numeric:tabular-nums}.err{color:#c0392b}
"""


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _clock(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def _money(value: float | None) -> str:
    return "—" if value is None else f"₹{value:,.2f}"


def _native(cost: str | None) -> str:
    """The cost in dollars under the rupee figure, for a model priced in dollars."""
    return "" if not cost or cost.startswith("₹") else f"<div class=muted>{cost}</div>"


def _call_difference(call: Call, sarvam: str, model: str) -> float | None:
    return difference(call.runs[sarvam].words_by_chunk, call.runs[model].words_by_chunk, transliterated=True).wer


def render(calls: Sequence[Call], summaries: Sequence[ModelSummary], models: Sequence[str], settings: Settings) -> str:
    rate = "USD_INR_RATE is not set, so dollar prices are not shown in rupees."
    if settings.usd_inr_rate:
        source = settings.usd_inr_source or "source not given"
        rate = f"Dollar prices are shown in rupees at ₹{settings.usd_inr_rate:g} per dollar ({source})."
    rows = "".join(
        f"<tr><td><b>{html.escape(s.model_id)}</b>{''.join(f'<div class=err>{html.escape(f)}</div>' for f in s.failed)}"
        f"</td><td>{html.escape(s.price)}</td><td class=n>{_money(s.inr_per_audio_hour)}</td>"
        f"<td class=n>{_money(s.cost_inr)}{_native(s.cost_native)}</td>"
        f"<td class=n>{'—' if s.real_time_factor is None else f'{s.real_time_factor * 60:.1f} s'}</td>"
        f"<td class=n>{'Reference' if s.model_id.startswith(SARVAM + '/') else _pct(s.difference_translit)}</td>"
        f"<td class=n>{'—' if s.model_id.startswith(SARVAM + '/') else _pct(s.difference_raw)}</td></tr>"
        for s in summaries
    )  # fmt: skip
    sources = "".join(f"<li><b>{html.escape(s.model_id)}</b>: {html.escape(s.price_source)}</li>"
                      for s in summaries if s.price_source)  # fmt: skip
    total_min = summaries[0].sent_minutes if summaries else 0
    parts = [
        f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Speech-to-text comparison</title>
<style>{_CSS}</style></head><body><main>
<h1>Speech-to-text comparison</h1>
<p class=muted>{len(calls)} calls, {total_min:.1f} minutes of speech, the same audio pieces sent to every model.
Made {datetime.now(UTC).strftime("%d %b %Y, %H:%M UTC")}.</p>
<div class="card note"><b>How to read this.</b> “Differs from Sarvam” counts the words a model wrote differently from
Sarvam (changed, missing or extra), as a share of Sarvam's words. It is <b>not accuracy</b>: nobody checked these
transcripts by hand, and Sarvam makes mistakes too. A low number means the model mostly agrees with Sarvam; a high
number means they disagree, and the call-by-call view below shows where (highlighted words). Listen to a few of those
moments to judge which model heard it right. “Ignoring script” treats Hindi in Devanagari and in Roman letters as the
same word; “as written” does not.</div>
<div class=card><table><tr><th>Model</th><th>Published price</th><th>Cost per hour of audio</th>
<th>Cost of these calls</th><th>Time to transcribe 1 min</th><th>Differs from Sarvam (ignoring script)</th>
<th>Differs from Sarvam (as written)</th></tr>{rows}</table>
<p class=muted>{html.escape(rate)} Cost counts the audio sent (speech only; silences are cut before transcription,
as in the app). Time is this machine's or the provider's processing time, added over all pieces.</p>
<details><summary>Price sources</summary><ul>{sources}</ul></details></div>"""
    ]
    for call in calls:
        recording = call.recording
        name = recording.client_name or recording.file_name or recording.id
        when = recording.recorded_at.strftime("%d %b %Y") if recording.recorded_at else ""
        present = [m for m in models if m in call.runs and call.runs[m].error is None]
        sarvam = next((m for m in present if m.startswith(SARVAM + "/")), None)
        head = "".join(f"<th>{html.escape(m)}</th>" for m in present)
        body = []
        for index, chunk in enumerate(call.chunks):
            ref = call.runs[sarvam].words_by_chunk[index] if sarvam else []
            cells = []
            for model in present:
                words = call.runs[model].words_by_chunk[index]
                text = (" ".join(html.escape(w.text) for w in words) if model == sarvam
                        else marked(ref, words))  # fmt: skip
                cells.append(f"<td>{text or '<span class=muted>(nothing)</span>'}</td>")
            start = call.segment_map.compact_to_original(chunk.owned_start_ms)
            body.append(f"<tr><td class=t>{_clock(start)}</td>{''.join(cells)}</tr>")
        diffs = " · ".join(
            f"{html.escape(m)}: {_pct(_call_difference(call, sarvam, m))}" for m in present if sarvam and m != sarvam
        )
        parts.append(f"""<details><summary>{html.escape(name)} <span class=muted>· {when} ·
{(recording.speech_ms or 0) / 60_000:.1f} min of speech · differs from Sarvam: {diffs or "—"}</span></summary>
<div class=card><table><tr><th>Time</th>{head}</tr>{"".join(body)}</table></div></details>""")
    parts.append("</main></body></html>")
    return "\n".join(parts)


# --- Main ---


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant", required=True, help="tenant id, e.g. demo-company")
    parser.add_argument(
        "--models", required=True, help="comma-separated provider[:model], e.g. openai,qwen,whisper:small"
    )
    parser.add_argument("--recordings", help="comma-separated recording ids (default: the latest --latest)")
    parser.add_argument("--latest", type=int, default=5, help="how many recent completed calls (default 5)")
    parser.add_argument("--workers", type=int, default=4, help="parallel requests per hosted model (default 4)")
    parser.add_argument("--out", type=Path, help="output folder (default eval/reports/asr-compare-<date>)")
    args = parser.parse_args(argv)
    from sabha_workers.tasks import s3_client  # the worker's S3 client: same settings and bucket

    settings = load_settings()
    specs = [parse_spec(s) for s in args.models.split(",") if s.strip()]
    providers = [build_provider(name, settings, model) for name, model in specs if name != SARVAM]
    sarvam_id = model_id_for(SARVAM, settings)
    models = [sarvam_id, *(p.model_id for p in providers)]
    out = args.out or EVAL_DIR / "reports" / f"asr-compare-{datetime.now(UTC).date().isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    s3 = s3_client(settings)
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        repo = SyncTenantRepo(client[settings.mongo_db], "recordings", args.tenant, Recording)
        if args.recordings:
            ids = [i.strip() for i in args.recordings.split(",") if i.strip()]
            recordings = repo.find({"_id": {"$in": ids}})
        else:
            query = {"status": RecordingStatus.COMPLETED.value, "source": {"$ne": "transcript"},
                     "audio_deleted_at": None}  # fmt: skip
            recordings = repo.find(query, sort=[("created_at", -1)], limit=args.latest)
    finally:
        client.close()
    calls: list[Call] = []
    with tempfile.TemporaryDirectory(prefix="sabha-asr-compare-") as tmp:
        for recording in recordings:
            label = recording.client_name or recording.file_name or recording.id
            try:
                call, compact, asr = load_call(s3, settings, recording, Path(tmp))
            except (FileNotFoundError, KeyError, ValueError) as exc:
                print(f"skip {label}: {exc}", file=sys.stderr)
                continue
            sarvam_words = [Word.from_record(w) for w in asr["words"]]
            asr_model = asr.get("model") if isinstance(asr.get("model"), str) else sarvam_id
            if asr_model != sarvam_id:
                print(f"note {label}: saved transcript is from {asr_model}, shown as the reference", file=sys.stderr)
            call.runs[sarvam_id] = ModelRun(by_chunk(call.chunks, sarvam_words),
                                            sent_ms=sum(c.duration_ms for c in call.chunks))  # fmt: skip
            for provider in providers:
                workers = 1 if provider.name == "whisper" else args.workers
                print(f"{label}: {provider.model_id} ({len(call.chunks)} pieces)", file=sys.stderr)
                call.runs[provider.model_id] = run_model(provider, call, compact, out, workers, settings.asr_language)
                if call.runs[provider.model_id].error:
                    print(f"  failed: {call.runs[provider.model_id].error}", file=sys.stderr)
            calls.append(call)
    if not calls:
        print("no calls to compare", file=sys.stderr)
        return 1
    summaries = [summarise(m, calls, settings.usd_inr_rate) for m in models]
    (out / "summary.json").write_text(json.dumps([s.__dict__ for s in summaries], ensure_ascii=False, indent=1),
                                      encoding="utf-8")  # fmt: skip
    (out / "index.html").write_text(render(calls, summaries, models, settings), encoding="utf-8")
    for s in summaries:
        print(f"{s.model_id:40} {s.price:34} per audio hour {_money(s.inr_per_audio_hour):>10}  "
              f"differs from Sarvam {_pct(s.difference_translit):>6}", file=sys.stderr)  # fmt: skip
    print(f"Report: {out / 'index.html'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
