"""Lint tests for golden rule 1: no raw MongoDB access outside the repository (plan task P1.6).

1. Only the modules in RAW_ACCESS_ALLOWED may call collection or database methods (`find`, `aggregate`,
   `insert_one`, `get_collection`, `watch`, ...) or index a client or database (`db["recordings"]`).
2. Only the modules in SYSTEM_REPO_ALLOWED may import SystemRepo or SyncSystemRepo, the unscoped repositories for the
   `tenants`, `outbox` and `identities` collections (ADR 0002).

Both scan apps/, packages/ and scripts/ with `ast`, skipping test directories. The checks look at method names, not
types, so a method that merely shares a name (say `str.find`) needs a different name or an entry in the allow-list
with its reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("apps", "packages", "scripts")

MONGO_METHODS = frozenset(
    {
        "aggregate", "bulk_write", "count_documents", "create_index", "create_indexes", "delete_many", "delete_one",
        "distinct", "drop", "drop_collection", "drop_database", "estimated_document_count", "find", "find_one",
        "find_one_and_delete", "find_one_and_replace", "find_one_and_update", "get_collection", "get_database",
        "insert_many", "insert_one", "list_collection_names", "replace_one", "update_many", "update_one", "watch",
    }
)  # fmt: skip

# Path (relative to the repo root) → why it may touch collections directly.
RAW_ACCESS_ALLOWED = {
    "packages/core/sabha_core/repo.py": "the tenant-scoped and system repositories themselves",
    "packages/core/sabha_core/indexes.py": "creates indexes at start-up; reads no documents",
    "apps/api/sabha_api/resources.py": "opens the database handle once at start-up; reads no documents",
}

SYSTEM_REPO_ALLOWED = {
    "packages/core/sabha_core/repo.py": "defines them",
    "apps/workers/sabha_workers/relay.py": "the outbox relay reads every tenant's events (P2.5)",
    "apps/api/sabha_api/auth/directory.py": "login looks up identities before the tenant is known (ADR 0002)",
}
SYSTEM_REPO_ALLOWED_PREFIXES = {
    "scripts/admin/": "operator scripts: create tenants, restore drills (P7.3)",
}

SYSTEM_REPO_NAMES = frozenset({"SystemRepo", "SyncSystemRepo"})


def source_files() -> list[Path]:
    files = []
    for top in SCANNED:
        for path in sorted((ROOT / top).rglob("*.py")):
            parts = path.relative_to(ROOT).parts
            if any(part in {"tests", "node_modules", ".venv", "__pycache__"} for part in parts):
                continue
            files.append(path)
    return files


def raw_access(source: str) -> list[tuple[int, str]]:
    """(line, what) for every call of a MongoDB collection method and every subscript of a client or database."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in MONGO_METHODS:
            found.append((node.lineno, f".{node.func.attr}()"))
        elif isinstance(node, ast.Subscript) and _looks_like_database(node.value):
            found.append((node.lineno, f"{ast.unparse(node.value)}[...]"))
    return found


def _looks_like_database(node: ast.expr) -> bool:
    # Lower-case names only: `AsyncMongoClient[dict[str, Any]]` is a type annotation, not a collection lookup.
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
    lowered = name.lower()
    return bool(name) and not name[0].isupper() and any(k in lowered for k in ("mongo", "client", "db", "database"))


def system_repo_imports(source: str) -> list[int]:
    """Lines that import SystemRepo/SyncSystemRepo, or import sabha_core.repo as a module (which would reach them)."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "sabha_core.repo":
            if any(alias.name in SYSTEM_REPO_NAMES or alias.name == "*" for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "sabha_core":
            if any(alias.name == "repo" for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.Import) and any(alias.name == "sabha_core.repo" for alias in node.names):
            lines.append(node.lineno)
    return lines


# --- The checks themselves ---


def test_no_raw_collection_access_outside_the_repository() -> None:
    offenders = []
    for path in source_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in RAW_ACCESS_ALLOWED:
            continue
        offenders += [f"{rel}:{line} {what}" for line, what in raw_access(path.read_text())]
    assert not offenders, "use TenantRepo (sabha_core.repo) instead of raw collection access:\n" + "\n".join(offenders)


def test_system_repo_is_imported_only_where_allowed() -> None:
    offenders = []
    for path in source_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in SYSTEM_REPO_ALLOWED or rel.startswith(tuple(SYSTEM_REPO_ALLOWED_PREFIXES)):
            continue
        offenders += [f"{rel}:{line}" for line in system_repo_imports(path.read_text())]
    assert not offenders, "SystemRepo is for the outbox relay, login and admin scripts only:\n" + "\n".join(offenders)


def test_the_scan_sees_the_code_it_must_police() -> None:
    scanned = {path.relative_to(ROOT).as_posix() for path in source_files()}
    assert "packages/core/sabha_core/repo.py" in scanned
    assert "apps/api/sabha_api/main.py" in scanned
    assert not any("/tests/" in f"/{path}" for path in scanned)


# --- The detectors catch what they should (so a passing check means something) ---


@pytest.mark.parametrize(
    "snippet",
    [
        "db.recordings.find({})",
        "await client.sabha.recordings.find_one({'_id': rid})",
        "collection.aggregate([])",
        "db['recordings']",
        "self._db['people']",
        "mongo_client.get_database('sabha').get_collection('people')",
        "request.app.state.resources.mongo['sabha']",
        "coll.update_many({}, {'$set': {'x': 1}})",
        "db.outbox.watch()",
    ],
)
def test_raw_access_detector_flags(snippet: str) -> None:
    assert raw_access(snippet)


@pytest.mark.parametrize(
    "snippet",
    [
        "client: AsyncMongoClient[dict[str, Any]] = make()",
        "repo.count({})",
        "values[0]",
        "store.principal_for(identity)",
    ],
)
def test_raw_access_detector_ignores(snippet: str) -> None:
    assert raw_access(snippet) == []


@pytest.mark.parametrize(
    "snippet",
    [
        "from sabha_core.repo import SystemRepo",
        "from sabha_core.repo import TenantRepo, SyncSystemRepo",
        "from sabha_core.repo import *",
        "from sabha_core import repo",
        "import sabha_core.repo",
    ],
)
def test_system_repo_detector_flags(snippet: str) -> None:
    assert system_repo_imports(snippet)


def test_system_repo_detector_allows_the_tenant_repo() -> None:
    assert system_repo_imports("from sabha_core.repo import TenantRepo, SyncTenantRepo, TenantViolationError") == []
