"""Amazon Transcribe batch jobs (docs/adr/0012-more-asr-providers.md).

Each chunk of a batch is uploaded as WAV to `s3://{bucket}/sabha-asr/{run}/{chunk_id}.wav` in the configured region
(default ap-south-1, Mumbai), one transcription job is started per chunk, and the jobs are polled together until
all finish. The transcript JSON is read from the job's TranscriptFileUri (Amazon's own output bucket, a pre-signed
https URL). The uploads and the jobs are deleted afterwards, whatever happened.

Language: with no hint ("unknown"), each job identifies the languages itself among LANGUAGE_OPTIONS (Hindi and Indian
English, switching within a chunk allowed). A job that fails language identification (very short audio) is run once
more with Hindi (hi-IN). A BCP-47 hint is used as the job's language directly.

Output: `results.items`, each a pronunciation (a word, with start_time/end_time in seconds and a confidence) or a
punctuation mark (joined to the word before it). So word_timing is "word".

Errors: AWS client errors that say waiting helps (throttling, service unavailable) are retryable; bad credentials,
a missing bucket or a failed job are not. Reasons name the AWS error code or job failure only.

Credentials: the explicit key pair from settings when given, else boto3's own chain (environment, profile, role).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError
from sabha_asr.words import Word

NAME = "aws"
DEFAULT_MODEL = "transcribe"
MAX_CHUNK_MS = 29_500
LANGUAGE_OPTIONS = ("hi-IN", "en-IN")
POLL_S = 2.0
JOB_TIMEOUT_S = 900.0
_RETRYABLE_CODES = frozenset({"ThrottlingException", "LimitExceededException", "InternalFailureException",
                              "ServiceUnavailable", "SlowDown", "RequestTimeout"})  # fmt: skip

log = logging.getLogger("sabha.asr.aws")


class AwsTranscribeProvider:
    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        language: str = "unknown",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        transcribe_client: Any = None,
        s3_client: Any = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not bucket:
            raise ValueError("an S3 bucket for Amazon Transcribe is required")
        self._bucket = bucket
        self._region = region
        self._language = language
        if transcribe_client is None or s3_client is None:
            import boto3

            session = boto3.session.Session(aws_access_key_id=access_key_id,
                                            aws_secret_access_key=secret_access_key, region_name=region)  # fmt: skip
            transcribe_client = transcribe_client or session.client("transcribe")
            s3_client = s3_client or session.client("s3")
        self._transcribe = transcribe_client
        self._s3 = s3_client
        self._http = http or httpx.Client(timeout=60.0)
        self._sleep = sleep

    @property
    def name(self) -> str:
        return NAME

    @property
    def model_id(self) -> str:
        return f"{NAME}/{DEFAULT_MODEL}@{self._region}"

    @property
    def word_timing(self) -> WordTiming:
        return "word"

    @property
    def max_chunk_ms(self) -> int:
        return MAX_CHUNK_MS

    def close(self) -> None:
        self._http.close()

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        run = uuid.uuid4().hex[:12]
        keys = {c.chunk_id: f"sabha-asr/{run}/{c.chunk_id}.wav" for c in chunks}
        jobs: dict[str, str] = {}
        try:
            for chunk in chunks:
                if chunk.duration_ms > MAX_CHUNK_MS:
                    raise ValueError(f"chunk {chunk.chunk_id!r} is {chunk.duration_ms} ms; the limit is {MAX_CHUNK_MS}")
                self._aws(self._s3.put_object, Bucket=self._bucket, Key=keys[chunk.chunk_id], Body=chunk.wav,
                          ContentType="audio/wav")  # fmt: skip
            for index, chunk in enumerate(chunks):
                jobs[chunk.chunk_id] = self._start(f"sabha-{run}-{index}", keys[chunk.chunk_id], chunk.language)
            done = self._wait(jobs)
            for index, chunk in enumerate(chunks):
                job = done[chunk.chunk_id]
                if job["TranscriptionJobStatus"] == "FAILED" and (chunk.language or self._language) == "unknown":
                    log.warning("Amazon Transcribe could not identify the language; trying again with hi-IN",
                                extra={"chunk_id": chunk.chunk_id})  # fmt: skip
                    retry = self._start(f"sabha-{run}-{index}-hi", keys[chunk.chunk_id], "hi-IN")
                    jobs[chunk.chunk_id + "#hi"] = retry
                    done[chunk.chunk_id] = self._wait({chunk.chunk_id: retry})[chunk.chunk_id]
            return [self._result(chunk, done[chunk.chunk_id]) for chunk in chunks]
        finally:
            self._clean(keys.values(), jobs.values())

    def _start(self, job_name: str, key: str, language: str | None) -> str:
        hint = language or self._language
        options: dict[str, Any] = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": f"s3://{self._bucket}/{key}"},
            "MediaFormat": "wav",
            "MediaSampleRateHertz": 16_000,
        }
        if hint == "unknown":
            options |= {"IdentifyMultipleLanguages": True, "LanguageOptions": list(LANGUAGE_OPTIONS)}
        else:
            options["LanguageCode"] = hint
        self._aws(self._transcribe.start_transcription_job, **options)
        return job_name

    def _wait(self, jobs: dict[str, str]) -> dict[str, dict[str, Any]]:
        deadline = time.monotonic() + JOB_TIMEOUT_S
        pending, done = dict(jobs), {}
        while pending:
            for chunk_id, name in list(pending.items()):
                job = self._aws(self._transcribe.get_transcription_job, TranscriptionJobName=name)["TranscriptionJob"]
                if job["TranscriptionJobStatus"] in ("COMPLETED", "FAILED"):
                    done[chunk_id] = job
                    del pending[chunk_id]
            if pending:
                if time.monotonic() > deadline:
                    raise ProviderError(NAME, f"{len(pending)} jobs still running after {JOB_TIMEOUT_S:.0f} s",
                                        retryable=True)  # fmt: skip
                self._sleep(POLL_S)
        return done

    def _result(self, chunk: AudioChunk, job: dict[str, Any]) -> ChunkResult:
        if job["TranscriptionJobStatus"] != "COMPLETED":
            reason = str(job.get("FailureReason", "unknown"))[:200]
            raise ProviderError(NAME, f"job failed: {reason}", retryable=False)
        try:
            response = self._http.get(job["Transcript"]["TranscriptFileUri"])
        except httpx.HTTPError as exc:
            raise ProviderError(NAME, f"transcript download failed ({type(exc).__name__})", retryable=True) from exc
        if response.status_code != 200:
            raise ProviderError(NAME, f"transcript download HTTP {response.status_code}", retryable=True)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(NAME, "transcript is not JSON", retryable=False) from exc
        language = job.get("LanguageCode") or _main_language(job)
        return parse(chunk, body, language)

    def _clean(self, keys: Any, jobs: Any) -> None:
        for name in jobs:
            try:
                self._transcribe.delete_transcription_job(TranscriptionJobName=name)
            except Exception:  # cleanup must not hide the real outcome; logged below
                log.warning("could not delete a transcription job", extra={"job": name})
        for key in keys:
            try:
                self._s3.delete_object(Bucket=self._bucket, Key=key)
            except Exception:  # as above
                log.warning("could not delete an uploaded chunk", extra={"key": key})

    def _aws(self, call: Callable[..., Any], **kwargs: Any) -> Any:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return call(**kwargs)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "unknown"))
            raise ProviderError(NAME, f"AWS {code}", retryable=code in _RETRYABLE_CODES) from exc
        except BotoCoreError as exc:
            raise ProviderError(NAME, f"AWS client error ({type(exc).__name__})", retryable=True) from exc


def _main_language(job: dict[str, Any]) -> str | None:
    found = job.get("LanguageCodes") or []
    best = max(found, key=lambda item: item.get("DurationInSeconds", 0), default=None)
    code = best.get("LanguageCode") if isinstance(best, dict) else None
    return code if isinstance(code, str) else None


def parse(chunk: AudioChunk, body: Any, language: str | None) -> ChunkResult:
    try:
        items = body["results"]["items"]
    except (KeyError, TypeError) as exc:
        raise ProviderError(NAME, "transcript has no items", retryable=False) from exc
    words: list[Word] = []
    for item in items:
        try:
            alternative = item["alternatives"][0]
            text = str(alternative["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(NAME, "an item has no content", retryable=False) from exc
        if item.get("type") == "punctuation":
            if words:
                last = words[-1]
                words[-1] = Word(last.text + text, last.start_ms, last.end_ms, last.confidence)
            continue
        try:
            start = min(max(round(float(item["start_time"]) * 1000), 0), chunk.duration_ms)
            end = min(max(round(float(item["end_time"]) * 1000), start), chunk.duration_ms)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(NAME, "a word has no times", retryable=False) from exc
        confidence = alternative.get("confidence")
        try:
            score = None if confidence in (None, "") else min(max(float(confidence), 0.0), 1.0)
        except (TypeError, ValueError):
            score = None
        words.append(Word(text, start, end, score))
    return ChunkResult(
        chunk_id=chunk.chunk_id,
        text=" ".join(word.text for word in words),
        words=tuple(words),
        languages=(LanguageSpan(0, chunk.duration_ms, language),),
    )
