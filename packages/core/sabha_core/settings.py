"""Application settings, loaded from environment variables (and a local `.env` file).

Call `get_settings()` once at start-up. A missing or invalid value raises `SettingsError`, which names each
problem variable but never echoes a value, so secrets cannot leak into logs or tracebacks. Secret fields are
`SecretStr`: they print as `**********` and must be read with `.get_secret_value()` at the point of use.

Every variable is documented in `.env.example`.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from sabha_core.timemap import DEFAULT_END_PAD_MS, DEFAULT_MERGE_GAP_MS

INDIA_REGION = "ap-south-1"
"""The only AWS region allowed in staging and production (golden rule 12)."""

AppEnv = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

_DEPLOYED_ENVS: frozenset[str] = frozenset({"staging", "production"})
_VERSION_TAG = re.compile(r"^[A-Za-z0-9._-]+$")
_GIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SettingsError(RuntimeError):
    """Configuration is missing or invalid. The message lists variable names only, never values."""


def _check_url(value: str, schemes: tuple[str, ...], what: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in schemes or not parts.hostname:
        raise ValueError(f"{what} must be a URL starting with {' or '.join(s + '://' for s in schemes)}")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # `KEY=` in .env counts as unset, so required values fail fast
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,  # keep raw values (possibly secrets) out of validation errors
    )

    # Application
    app_env: AppEnv
    log_level: LogLevel = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    git_sha: str | None = None  # set at image build time; shown by GET /v1/meta

    # MongoDB (must be a replica set: transactions and change streams are required)
    mongo_uri: SecretStr
    mongo_db: str = "sabha"

    # Redis (Celery broker and cache)
    redis_url: SecretStr

    # API rate limits (P7.2, sabha_api.ratelimit): requests per minute, and how far past that a burst may go
    rate_limit_tenant_per_minute: int = Field(default=600, ge=1)
    rate_limit_user_per_minute: int = Field(default=120, ge=1)
    rate_limit_burst_factor: float = Field(default=1.5, ge=1.0, le=10.0)

    # Object storage: S3 on AWS, RustFS locally. Three buckets so each gets its own lifecycle and access rules.
    s3_bucket_audio: str  # uploaded originals, short retention
    s3_bucket_artefacts: str  # pipeline outputs: {tenant_id}/{recording_id}/{stage}@{version}/
    s3_bucket_backups: str
    s3_region: str = INDIA_REGION
    s3_endpoint_url: str | None = None
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    # Browser uploads (P2.1): direct to the audio bucket with presigned multipart URLs (golden rule 2). S3 needs
    # parts of at least 5 MiB (except the last) and at most 10 000 parts.
    upload_max_bytes: int = Field(default=1024**3, ge=1)  # 1 GiB
    upload_part_size_bytes: int = Field(default=16 * 1024**2, ge=5 * 1024**2)
    upload_url_expiry_s: int = Field(default=900, ge=60, le=3600)  # each presigned part URL
    playback_url_expiry_s: int = Field(default=900, ge=60, le=3600)  # each presigned playback URL (P5.7b)

    # Authentication (OIDC)
    oidc_issuer: str
    oidc_audience: str
    oidc_client_id: str

    # Speech recognition (packages/asr, docs/adr/0006-asr-sarvam.md). The speech worker refuses to start without a
    # provider. Fallbacks are tried in order only when listed here, and every use is logged (golden rule 7).
    asr_provider: str | None = None
    asr_fallbacks: Annotated[list[str], NoDecode] = Field(default_factory=list)
    asr_model: str | None = None  # the provider's default when unset
    asr_language: str = "unknown"  # a BCP-47 hint such as hi-IN, or "unknown" to detect the language
    sarvam_api_key: SecretStr | None = None
    sarvam_base_url: str = "https://api.sarvam.ai"

    # LLM gateway (packages/llm, plan task P5.1). Models are "<provider>:<model>", e.g. "openai:o3-mini". Fallbacks
    # are per task and only used when listed: {"score_dimension": ["openai:o4-mini"]} (golden rule 7). Token
    # budgets are per UTC day; unset means no limit (the owner sets the numbers; none are assumed here).
    llm_model_small: str = "openai:o3-mini"
    llm_model_mid: str = "openai:o3-mini"
    llm_fallbacks: dict[str, list[str]] = Field(default_factory=dict)
    llm_timeout_s: float = Field(default=120.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    llm_tenant_daily_token_budget: int | None = Field(default=None, ge=1)
    llm_global_daily_token_budget: int | None = Field(default=None, ge=1)

    # LLM providers (docs/llm-providers.md). Data-residency approval comes first (golden rule 12).
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None

    # Observability
    otel_exporter_otlp_endpoint: str | None = None  # tracing is off when unset
    sentry_dsn: SecretStr | None = None
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None

    # Email (Amazon SES). Without SES_SENDER no email is sent (the notify task logs that and skips).
    ses_region: str = INDIA_REGION
    ses_sender: str | None = None
    web_base_url: str = "http://localhost:5173"  # links in emails point here

    # Speech workers
    gpu_device_id: int | None = Field(default=None, ge=0)

    # Rubric files (P3.6, P5.7): <rubrics_dir>/<rubric id>.yaml. Relative paths are from the working directory (the
    # repo root in development); the worker images set /app/rubrics.
    rubrics_dir: str = "rubrics"

    # Speaker diarization (P3.4). "fake" (a scripted diarizer) is only allowed when APP_ENV=test.
    diarizer: Literal["pyannote", "fake"] = "pyannote"
    diarization_device: str = Field(default="cpu", pattern=r"^(cpu|cuda(:[0-9]+)?)$")
    diarization_batch_size: int = Field(default=8, ge=1, le=128)  # 8: half the CPU memory of pyannote's 32
    diarization_model_dir: str | None = None  # None: ~/.cache/sabha/models (`make models-speech`)
    hf_token: SecretStr | None = None  # Hugging Face read token: only to download the pyannote model, never at runtime

    # Voice activity detection (P3.3, preprocess step 2). Unmeasured starting values: tune them on the gold set.
    vad_model_path: str | None = None  # None: ~/.cache/sabha/models (`make models`); the worker image sets its own
    vad_threshold: float = Field(default=0.5, gt=0, lt=1)  # a 32 ms window at or above this is speech
    vad_min_speech_ms: int = Field(default=250, ge=0)  # shorter speech regions are dropped
    vad_min_silence_ms: int = Field(default=100, ge=0)  # speech ends after this much silence
    vad_end_pad_ms: int = Field(
        default=DEFAULT_END_PAD_MS, ge=0
    )  # added to each region's end: Silero tends to clip word ends
    vad_merge_gap_ms: int = Field(default=DEFAULT_MERGE_GAP_MS, ge=0)  # regions closer than this become one segment

    # Celery workers (P2.4). A task not acknowledged within the visibility timeout is handed to another worker, so it
    # must exceed the longest stage (GPU stages on long lessons); the CPU workers may use a shorter one.
    celery_visibility_timeout_s: int = Field(default=4 * 3600, ge=1)
    stage_max_attempts: int = Field(default=6, ge=1, le=20)  # the first try plus up to 5 retries
    stuck_after_s: int = Field(default=30 * 60, ge=60)  # a running stage with no heartbeat this long is re-sent

    # Artefact versions: part of every artefact path, {tenant_id}/{recording_id}/{stage}@{version}/
    artefact_version_preprocess: str = "v1"
    artefact_version_diarize: str = "v1"
    artefact_version_transcribe: str = "v1"
    artefact_version_analyze: str = "v1"

    @field_validator("asr_fallbacks", mode="before")
    @classmethod
    def _split_fallbacks(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _check_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            parts = urlsplit(origin)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.path not in ("", "/"):
                raise ValueError("each origin must look like https://host[:port], comma-separated")
        return [origin.rstrip("/") for origin in value]

    @field_validator("mongo_uri")
    @classmethod
    def _check_mongo_uri(cls, value: SecretStr) -> SecretStr:
        uri = value.get_secret_value()
        _check_url(uri, ("mongodb", "mongodb+srv"), "MONGO_URI")
        # mongodb+srv (Atlas) always resolves to a replica set; a plain mongodb:// URI must name one.
        if uri.startswith("mongodb://") and "replicaSet" not in parse_qs(urlsplit(uri).query):
            raise ValueError("MONGO_URI must include ?replicaSet=<name>; Sabha needs a replica set")
        return value

    @field_validator("redis_url")
    @classmethod
    def _check_redis_url(cls, value: SecretStr) -> SecretStr:
        _check_url(value.get_secret_value(), ("redis", "rediss"), "REDIS_URL")
        return value

    @field_validator("git_sha")
    @classmethod
    def _check_git_sha(cls, value: str | None) -> str | None:
        if value is not None and not _GIT_SHA.match(value):
            raise ValueError("GIT_SHA must be 7 to 40 lowercase hex characters")
        return value

    @field_validator(
        "s3_endpoint_url",
        "langfuse_host",
        "openai_base_url",
        "otel_exporter_otlp_endpoint",
        "sarvam_base_url",
        "web_base_url",
    )
    @classmethod
    def _check_http_url(cls, value: str | None) -> str | None:
        return None if value is None else _check_url(value, ("http", "https"), "value")

    @field_validator("oidc_issuer")
    @classmethod
    def _check_issuer(cls, value: str) -> str:
        return _check_url(value, ("http", "https"), "OIDC_ISSUER").rstrip("/")

    @field_validator("ses_sender")
    @classmethod
    def _check_sender(cls, value: str | None) -> str | None:
        if value is not None and not _EMAIL.match(value):
            raise ValueError("SES_SENDER must be an email address")
        return value

    @field_validator(
        "artefact_version_preprocess",
        "artefact_version_diarize",
        "artefact_version_transcribe",
        "artefact_version_analyze",
    )
    @classmethod
    def _check_version_tag(cls, value: str) -> str:
        if not _VERSION_TAG.match(value):
            raise ValueError("artefact versions may contain only letters, digits, '.', '_' and '-'")
        return value

    @model_validator(mode="after")
    def _check_combinations(self) -> Settings:
        if self.diarizer == "fake" and self.app_env != "test":
            raise ValueError("DIARIZER=fake is for tests only (APP_ENV=test)")
        if (self.langfuse_public_key is None) != (self.langfuse_secret_key is None):
            raise ValueError("set both LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY, or neither")
        if self.langfuse_public_key is not None and self.langfuse_host is None:
            raise ValueError("LANGFUSE_HOST is required when Langfuse keys are set")
        if (self.s3_access_key_id is None) != (self.s3_secret_access_key is None):
            raise ValueError("set both S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY, or neither")
        if self.app_env in _DEPLOYED_ENVS:
            if self.s3_region != INDIA_REGION or self.ses_region != INDIA_REGION:
                raise ValueError(f"S3_REGION and SES_REGION must be {INDIA_REGION} in {self.app_env}")
            if self.s3_endpoint_url is not None:
                raise ValueError(f"S3_ENDPOINT_URL is for local RustFS only; leave it unset in {self.app_env}")
            if not self.oidc_issuer.startswith("https://"):
                raise ValueError(f"OIDC_ISSUER must use https in {self.app_env}")
            if self.openai_base_url is not None and not self.openai_base_url.startswith("https://"):
                raise ValueError(f"OPENAI_BASE_URL must use https in {self.app_env}")
            if not self.sarvam_base_url.startswith("https://"):
                raise ValueError(f"SARVAM_BASE_URL must use https in {self.app_env}")
            if "fake" in (self.asr_provider, *self.asr_fallbacks):
                raise ValueError(f"the fake ASR provider is for tests and local development, not {self.app_env}")
        if self.asr_provider is not None and self.asr_provider in self.asr_fallbacks:
            raise ValueError("ASR_FALLBACKS must not repeat ASR_PROVIDER")
        if len(set(self.asr_fallbacks)) != len(self.asr_fallbacks):
            raise ValueError("ASR_FALLBACKS lists a provider twice")
        if "sarvam" in (self.asr_provider, *self.asr_fallbacks) and self.sarvam_api_key is None:
            raise ValueError("SARVAM_API_KEY is required when Sarvam is the ASR provider or a fallback")
        return self


def _describe(exc: ValidationError) -> str:
    lines = []
    for error in exc.errors(include_input=False, include_url=False):
        name = ".".join(str(part) for part in error["loc"]).upper() or "settings"
        message = "missing" if error["type"] == "missing" else error["msg"].removeprefix("Value error, ")
        lines.append(f"  {name}: {message}")
    return "Invalid configuration (see .env.example):\n" + "\n".join(lines)


def load_settings(env_file: str | None = ".env") -> Settings:
    """Build settings from the environment and `env_file`, raising `SettingsError` on any problem."""
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]  # settings option mypy cannot see
    except ValidationError as exc:
        raise SettingsError(_describe(exc)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings, loaded once."""
    return load_settings()
