"""Shared vocabulary and a tiny Label Studio HTTP client for the gold-set scripts.

Used by import_tasks.py and export_gold.py (plan task P4.1). Standard library only, so the
scripts run without installing anything; P1.1 will fold eval/ into the uv workspace.

The names below must match infra/annotation/transcript_config.xml; tests/test_transcript_config.py
checks that they do.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

# ---------------------------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------------------------

# Recording types in the gold set. Only the pilot types: the labelling interface has speaker
# labels for teaching (Teacher, Student(s)) and reception (Receptionist, Caller) and nothing
# else. Adding a type means adding its speaker labels to transcript_config.xml first.
ALLOWED_TYPES: tuple[str, ...] = ("teaching", "reception")

# Language mix of a recording, as decided by the person who builds the manifest.
ALLOWED_LANGUAGE_MIX: tuple[str, ...] = ("english", "hindi", "hinglish")

# Columns of the import manifest CSV. Exactly these, in any order.
MANIFEST_COLUMNS: tuple[str, ...] = ("file", "tenant", "type", "language_mix", "room_type", "consent_ref")

# Label Studio label value (what annotators see) -> canonical speaker_role.
LABEL_TO_ROLE: dict[str, str] = {
    "Teacher": "teacher",
    "Student(s)": "students",
    "Receptionist": "receptionist",
    "Caller": "caller",
    "Other": "other",
    "Silence": "silence",
}
SPEAKER_ROLES: tuple[str, ...] = tuple(LABEL_TO_ROLE.values())
SILENCE_ROLE = "silence"

# Tag names in transcript_config.xml.
AUDIO_TAG_NAME = "audio"  # <Audio name="audio" value="$audio">
LABELS_TAG_NAME = "speaker"  # <Labels name="speaker" toName="audio">
TEXT_TAG_NAME = "transcript"  # <TextArea name="transcript" toName="audio" perRegion="true">

# Task data key that holds the audio URL (the $audio in the config).
AUDIO_DATA_KEY = "audio"

# Recording ids become file names (gold/<recording_id>.json), so keep them boring.
RECORDING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
# Tenant ids: same shape (slug or ObjectId-like).
TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
# room_type has no fixed list yet; require a lowercase snake_case token so reports group cleanly.
ROOM_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")

# Audio formats browsers can usually play; Label Studio streams the file to the browser as is.
AUDIO_EXTENSIONS: tuple[str, ...] = (".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".webm")

# Label Studio local-files serving (see infra/annotation/docker-compose.yml):
# LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/label-studio/files, audio mounted at /label-studio/files/audio.
LOCAL_FILES_DOCUMENT_ROOT = "/label-studio/files"
DEFAULT_AUDIO_PREFIX = "audio"
LOCAL_FILES_URL_PREFIX = "/data/local-files/?d="


def local_files_url(prefix: str, relative_path: str) -> str:
    """URL Label Studio uses to serve `<document root>/<prefix>/<relative_path>`."""
    d = f"{prefix.strip('/')}/{relative_path.lstrip('/')}"
    return LOCAL_FILES_URL_PREFIX + urllib.parse.quote(d, safe="/")


def audio_path_from_url(url: str) -> str:
    """Return the file path inside an audio URL: the `d` parameter for local-files URLs,
    otherwise the URL path. Percent-encoding is decoded."""
    parsed = urllib.parse.urlsplit(url)
    d_values = urllib.parse.parse_qs(parsed.query).get("d")
    if d_values:
        return d_values[0]
    return urllib.parse.unquote(parsed.path)


def recording_id_from_audio(url_or_path: str) -> str:
    """Recording id = audio file name without its last extension (like pathlib's Path.stem).
    The caller must still check it against RECORDING_ID_RE."""
    name = audio_path_from_url(url_or_path).rstrip("/").rsplit("/", 1)[-1]
    stem, dot, _ext = name.rpartition(".")
    return stem if dot else name


# ---------------------------------------------------------------------------------------------
# Label Studio HTTP client (urllib only)
# ---------------------------------------------------------------------------------------------

ENV_URL = "LABEL_STUDIO_URL"
ENV_TOKEN = "LABEL_STUDIO_API_KEY"  # noqa: S105  # env var name, not a secret; the official SDK reads it too
DEFAULT_URL = "http://localhost:8080"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class LabelStudioError(RuntimeError):
    """An API call failed. Messages never contain the token."""


def resolve_connection(url: str | None, token: str | None, env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Flag values win over environment variables. Raises LabelStudioError if no token."""
    env = os.environ if env is None else env
    base_url = (url or env.get(ENV_URL) or DEFAULT_URL).rstrip("/")
    api_token = token or env.get(ENV_TOKEN) or ""
    if not api_token.strip():
        raise LabelStudioError(
            f"no Label Studio API token: set {ENV_TOKEN} (preferred) or pass --token; "
            "see infra/annotation/README.md, 'Get an API token'"
        )
    return base_url, api_token.strip()


def check_base_url(base_url: str, allow_insecure_http: bool = False) -> None:
    """Refuse to send a token over plain HTTP to anything other than this machine."""
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise LabelStudioError(f"Label Studio URL must look like http(s)://host[:port], got {base_url!r}")
    if parsed.scheme == "http" and parsed.hostname not in LOOPBACK_HOSTS and not allow_insecure_http:
        raise LabelStudioError(
            f"refusing to send the API token over plain HTTP to {parsed.hostname}; "
            "use https, an SSH tunnel to localhost, or --allow-insecure-http if you really mean it"
        )


def is_personal_access_token(token: str) -> bool:
    """Personal access tokens are JWT refresh tokens (header.payload.signature).
    Legacy tokens are opaque hex strings."""
    return token.count(".") == 2 and token.startswith("eyJ")


class LabelStudioClient:
    """Minimal REST client.

    Auth (Label Studio docs, guide/access_tokens.md, 1.23.2):
    - personal access token: POST /api/token/refresh/ {"refresh": PAT} -> {"access": ...},
      then `Authorization: Bearer <access>` (access tokens are short-lived; we refresh on 401);
    - legacy token: `Authorization: Token <token>`.
    Both use the Authorization header, which is why there is no basic-auth proxy in front of
    Label Studio (infra/annotation/README.md).
    """

    def __init__(self, base_url: str, token: str, timeout: float = 120.0) -> None:
        if urllib.parse.urlsplit(base_url).scheme not in ("http", "https"):
            raise LabelStudioError(f"Label Studio URL must use http or https, got {base_url!r}")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._access: str | None = None

    def __repr__(self) -> str:  # never show the token
        return f"LabelStudioClient(base_url={self.base_url!r})"

    def _auth_header(self, refresh: bool = False) -> str:
        if not is_personal_access_token(self._token):
            return f"Token {self._token}"
        if self._access is None or refresh:
            body = self._raw("POST", "/api/token/refresh/", {"refresh": self._token}, auth=None)
            access = body.get("access") if isinstance(body, dict) else None
            if not isinstance(access, str) or not access:
                raise LabelStudioError("token refresh returned no access token")
            self._access = access
        return f"Bearer {self._access}"

    def _raw(self, method: str, path: str, payload: Any = None, auth: str | None = None) -> Any:
        url = self.base_url + path
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310  # scheme checked in __init__
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if auth is not None:
            request.add_header("Authorization", auth)
        try:
            # http(s) only (checked in __init__); callers also run check_base_url() for the plain-http rule.
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(500).decode("utf-8", "replace").strip()
            raise LabelStudioError(f"{method} {path} failed: HTTP {exc.code} {detail}") from None
        except urllib.error.URLError as exc:
            raise LabelStudioError(f"{method} {path} failed: {exc.reason}") from None
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise LabelStudioError(f"{method} {path} did not return JSON") from None

    def request(self, method: str, path: str, payload: Any = None) -> Any:
        try:
            return self._raw(method, path, payload, auth=self._auth_header())
        except LabelStudioError as exc:
            if "HTTP 401" in str(exc) and is_personal_access_token(self._token):
                return self._raw(method, path, payload, auth=self._auth_header(refresh=True))
            raise

    # --- endpoints used by the gold-set scripts (paths checked against Label Studio 1.23.2 urls.py) ---

    def export_tasks(self, project_id: int) -> list[dict[str, Any]]:
        """All tasks of a project, with annotations, in Label Studio JSON format
        (GET /api/projects/<id>/export?exportType=JSON&download_all_tasks=true)."""
        body = self.request("GET", f"/api/projects/{project_id}/export?exportType=JSON&download_all_tasks=true")
        if not isinstance(body, list):
            raise LabelStudioError("export did not return a JSON list of tasks")
        return body

    def import_tasks(self, project_id: int, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """POST /api/projects/<id>/import with a JSON list of {"data": {...}} tasks."""
        body = self.request("POST", f"/api/projects/{project_id}/import", tasks)
        return body if isinstance(body, dict) else {}

    def local_storages(self, project_id: int) -> list[dict[str, Any]]:
        """Local-files source storages of a project (GET /api/storages/localfiles/?project=<id>)."""
        body = self.request("GET", f"/api/storages/localfiles/?project={project_id}")
        if isinstance(body, dict) and isinstance(body.get("results"), list):
            body = body["results"]
        if not isinstance(body, list):
            raise LabelStudioError("storage list did not return a JSON list")
        return [item for item in body if isinstance(item, dict)]
