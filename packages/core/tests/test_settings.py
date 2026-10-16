"""Tests for sabha_core.settings: fail fast on bad config, never reveal secret values."""

from __future__ import annotations

import pytest

from sabha_core.settings import Settings, SettingsError, load_settings

MONGO_PASSWORD = "mongo-pa55-do-not-leak"
REDIS_PASSWORD = "redis-pa55-do-not-leak"
S3_SECRET = "s3-secret-do-not-leak"
LANGFUSE_SECRET = "lf-secret-do-not-leak"
SENTRY_DSN = "https://sentry-key-do-not-leak@sentry.example.com/1"
OPENAI_KEY = "sk-openai-do-not-leak"

SECRETS = [MONGO_PASSWORD, REDIS_PASSWORD, S3_SECRET, LANGFUSE_SECRET, SENTRY_DSN, OPENAI_KEY]

VALID_ENV = {
    "APP_ENV": "local",
    "MONGO_URI": f"mongodb://sabha:{MONGO_PASSWORD}@localhost:27017/?replicaSet=rs0",
    "REDIS_URL": f"redis://:{REDIS_PASSWORD}@localhost:6379/0",
    "S3_BUCKET_AUDIO": "sabha-audio",
    "S3_BUCKET_ARTEFACTS": "sabha-artefacts",
    "S3_BUCKET_BACKUPS": "sabha-backups",
    "S3_ENDPOINT_URL": "http://localhost:9000",
    "S3_ACCESS_KEY_ID": "rustfs",
    "S3_SECRET_ACCESS_KEY": S3_SECRET,
    "OIDC_ISSUER": "https://auth.example.com/",
    "OIDC_AUDIENCE": "https://api.sabha.example.com",
    "OIDC_CLIENT_ID": "web-client",
    "SENTRY_DSN": SENTRY_DSN,
    "LANGFUSE_HOST": "https://langfuse.example.com",
    "LANGFUSE_PUBLIC_KEY": "lf-public",
    "LANGFUSE_SECRET_KEY": LANGFUSE_SECRET,
    "CORS_ORIGINS": "http://localhost:5173, https://app.sabha.example.com/",
    "OPENAI_API_KEY": OPENAI_KEY,
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Start every test from exactly VALID_ENV, ignoring the developer's shell and .env file."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def load() -> Settings:
    return load_settings(env_file=None)


def assert_no_secrets(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text


def test_valid_environment_loads(env: pytest.MonkeyPatch) -> None:
    settings = load()

    assert settings.app_env == "local"
    assert settings.s3_region == "ap-south-1"
    assert settings.oidc_issuer == "https://auth.example.com"
    assert settings.cors_origins == ["http://localhost:5173", "https://app.sabha.example.com"]
    assert settings.mongo_uri.get_secret_value() == VALID_ENV["MONGO_URI"]


@pytest.mark.parametrize(
    "name",
    [
        "APP_ENV",
        "MONGO_URI",
        "REDIS_URL",
        "S3_BUCKET_AUDIO",
        "S3_BUCKET_ARTEFACTS",
        "S3_BUCKET_BACKUPS",
        "OIDC_ISSUER",
        "OIDC_AUDIENCE",
    ],
)
def test_missing_required_value_fails_fast_and_names_it(env: pytest.MonkeyPatch, name: str) -> None:
    env.delenv(name)

    with pytest.raises(SettingsError) as raised:
        load()

    assert f"{name}: missing" in str(raised.value)


def test_empty_required_value_counts_as_missing(env: pytest.MonkeyPatch) -> None:
    env.setenv("MONGO_URI", "")

    with pytest.raises(SettingsError, match="MONGO_URI: missing"):
        load()


def test_every_missing_value_is_reported_at_once(env: pytest.MonkeyPatch) -> None:
    env.delenv("MONGO_URI")
    env.delenv("REDIS_URL")

    with pytest.raises(SettingsError) as raised:
        load()

    assert "MONGO_URI: missing" in str(raised.value)
    assert "REDIS_URL: missing" in str(raised.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MONGO_URI", f"not-a-uri-{MONGO_PASSWORD}"),
        ("MONGO_URI", f"postgres://sabha:{MONGO_PASSWORD}@localhost/db"),
        ("REDIS_URL", f"http://:{REDIS_PASSWORD}@localhost:6379"),
        ("S3_ENDPOINT_URL", "localhost:9000"),
        ("OIDC_ISSUER", "auth.example.com"),
        ("CORS_ORIGINS", "https://app.example.com/some/path"),
    ],
)
def test_malformed_uri_is_rejected_without_echoing_it(env: pytest.MonkeyPatch, name: str, value: str) -> None:
    env.setenv(name, value)

    with pytest.raises(SettingsError) as raised:
        load()

    message = str(raised.value)
    assert name in message
    assert value not in message
    assert_no_secrets(message)


def test_mongo_uri_without_replica_set_is_rejected(env: pytest.MonkeyPatch) -> None:
    env.setenv("MONGO_URI", f"mongodb://sabha:{MONGO_PASSWORD}@localhost:27017/")

    with pytest.raises(SettingsError, match="replicaSet") as raised:
        load()

    assert_no_secrets(str(raised.value))


def test_atlas_srv_uri_needs_no_replica_set_parameter(env: pytest.MonkeyPatch) -> None:
    env.setenv("MONGO_URI", f"mongodb+srv://sabha:{MONGO_PASSWORD}@cluster0.example.mongodb.net/")

    assert load().mongo_uri.get_secret_value().startswith("mongodb+srv://")


def test_secrets_are_not_in_repr_str_or_json(env: pytest.MonkeyPatch) -> None:
    settings = load()

    assert_no_secrets(repr(settings))
    assert_no_secrets(str(settings))
    assert_no_secrets(settings.model_dump_json())


def test_validation_error_is_not_chained(env: pytest.MonkeyPatch) -> None:
    # A chained pydantic ValidationError would print a second traceback; keep the output to our message.
    env.delenv("MONGO_URI")

    with pytest.raises(SettingsError) as raised:
        load()

    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_must_stay_in_india(env: pytest.MonkeyPatch, app_env: str) -> None:
    env.setenv("APP_ENV", app_env)
    env.delenv("S3_ENDPOINT_URL")
    env.setenv("S3_REGION", "us-east-1")

    with pytest.raises(SettingsError, match="ap-south-1"):
        load()


def test_local_s3_endpoint_is_refused_in_production(env: pytest.MonkeyPatch) -> None:
    env.setenv("APP_ENV", "production")

    with pytest.raises(SettingsError, match="S3_ENDPOINT_URL"):
        load()


def test_langfuse_keys_must_come_in_pairs(env: pytest.MonkeyPatch) -> None:
    env.delenv("LANGFUSE_SECRET_KEY")

    with pytest.raises(SettingsError, match="LANGFUSE_SECRET_KEY") as raised:
        load()

    assert_no_secrets(str(raised.value))


def test_artefact_version_cannot_break_the_artefact_path(env: pytest.MonkeyPatch) -> None:
    env.setenv("ARTEFACT_VERSION_ANALYZE", "v1/../other")

    with pytest.raises(SettingsError, match="ARTEFACT_VERSION_ANALYZE"):
        load()


def deployed(env: pytest.MonkeyPatch, app_env: str = "production") -> None:
    env.setenv("APP_ENV", app_env)
    env.delenv("S3_ENDPOINT_URL")


def test_openai_key_is_loaded_and_kept_secret(env: pytest.MonkeyPatch) -> None:
    settings = load()
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == OPENAI_KEY
    assert_no_secrets(repr(settings))


def test_openai_base_url_must_be_https_when_deployed(env: pytest.MonkeyPatch) -> None:
    deployed(env)
    env.setenv("OPENAI_BASE_URL", "http://openai.example.com/v1")
    with pytest.raises(SettingsError, match="OPENAI_BASE_URL must use https"):
        load()


@pytest.mark.parametrize("value", ["abc", "ABCDEF1", "g123456", "0" * 41])
def test_git_sha_must_be_a_hex_commit(env: pytest.MonkeyPatch, value: str) -> None:
    env.setenv("GIT_SHA", value)
    with pytest.raises(SettingsError, match="GIT_SHA"):
        load()


def test_git_sha_and_otlp_endpoint_are_optional(env: pytest.MonkeyPatch) -> None:
    settings = load()
    assert settings.git_sha is None
    assert settings.otel_exporter_otlp_endpoint is None
    env.setenv("GIT_SHA", "0123abc")
    env.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    settings = load()
    assert (settings.git_sha, settings.otel_exporter_otlp_endpoint) == ("0123abc", "http://localhost:4318")
