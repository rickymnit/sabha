"""Access-token validation against the OIDC issuer (plan task P1.5, ADR 0002).

The web app signs users in with the provider (PKCE) and sends the access token as `Authorization: Bearer <token>`.
`TokenVerifier.verify` accepts a token only if:

- it is a JWT signed with RS256 by a key from the issuer's JWKS. `none` and HMAC are refused: with HMAC an attacker
  could sign a token using our public key as the secret;
- `iss` is our issuer, `aud` contains our audience, `exp` has not passed (LEEWAY_S allows for clock skew) and `sub`
  is present.

Signing keys: the JWKS URL comes from the issuer's discovery document. Keys are cached for JWKS_TTL_S. A token with an
unknown `kid` (the provider rotated its keys) triggers a refetch, at most once per JWKS_MIN_REFETCH_S so tokens with
made-up key ids cannot make us hammer the provider. If a refetch fails, cached keys stay in use and the failure is
logged; with no keys at all the API answers 503 `auth_unavailable`, never 401, so clients don't sign users out.

Only standard claims are read, so the code works with Auth0 or Keycloak. Auth0 issuers end in "/" and our settings
strip it, so `iss` is compared without a trailing slash.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from sabha_api.errors import ApiError, UnauthorizedError

log = logging.getLogger("sabha.api.auth")

ALGORITHMS = ["RS256"]
LEEWAY_S = 30
JWKS_TTL_S = 600.0
JWKS_MIN_REFETCH_S = 30.0
_HTTP_TIMEOUT_S = 5.0

FetchJson = Callable[[str], Awaitable[Mapping[str, Any]]]


async def fetch_json(url: str) -> Mapping[str, Any]:
    """GET a JSON object. Redirects are not followed: the discovery document and JWKS must be at the URLs given."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S, follow_redirects=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict):
        raise ValueError("expected a JSON object")
    return body


class InvalidTokenError(UnauthorizedError):
    """401 with the RFC 6750 challenge, so clients know to sign in again."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})


class AuthUnavailableError(ApiError):
    status, code, title = 503, "auth_unavailable", "Sign-in is unavailable"


@dataclass(frozen=True, slots=True)
class Identity:
    """Who the provider says the caller is. `issuer` is ours, normalised without a trailing slash."""

    issuer: str
    subject: str


class TokenVerifier:
    """Validates access tokens for one issuer and audience. Create one per process; it holds the key cache."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        *,
        fetch: FetchJson = fetch_json,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self._fetch = fetch
        self._clock = clock
        self._jwks_uri: str | None = None
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None  # last fetch attempt, successful or not
        self._lock = asyncio.Lock()

    async def verify(self, token: str) -> Identity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("The access token is malformed.") from exc
        if header.get("alg") not in ALGORITHMS:
            raise InvalidTokenError("The access token uses an unsupported signing algorithm.")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise InvalidTokenError("The access token has no key id.")
        key = await self._key(kid)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self.audience,
                leeway=LEEWAY_S,
                options={"require": ["exp", "iss", "sub", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise InvalidTokenError("The access token has expired.") from exc
        except jwt.InvalidAudienceError as exc:
            raise InvalidTokenError("The access token is not for this API.") from exc
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("The access token is not valid.") from exc
        issuer, subject = claims["iss"], claims["sub"]
        if not isinstance(issuer, str) or issuer.rstrip("/") != self.issuer:
            raise InvalidTokenError("The access token is from another issuer.")
        if not isinstance(subject, str) or not subject:
            raise InvalidTokenError("The access token has no subject.")
        return Identity(issuer=self.issuer, subject=subject)

    async def _key(self, kid: str) -> Any:
        if kid in self._keys and self._is_fresh():
            return self._keys[kid]
        async with self._lock:
            # Another request may have refreshed while we waited.
            if not (kid in self._keys and self._is_fresh()) and self._may_fetch():
                await self._refresh()
        if kid in self._keys:
            return self._keys[kid]
        if not self._keys:
            raise AuthUnavailableError("Sign-in keys could not be loaded. Try again shortly.")
        raise InvalidTokenError("The access token was signed by an unknown key.")

    def _is_fresh(self) -> bool:
        return self._fetched_at is not None and self._clock() - self._fetched_at < JWKS_TTL_S

    def _may_fetch(self) -> bool:
        return self._fetched_at is None or self._clock() - self._fetched_at >= JWKS_MIN_REFETCH_S

    async def _refresh(self) -> None:
        self._fetched_at = self._clock()
        try:
            if self._jwks_uri is None:
                self._jwks_uri = self._jwks_uri_from(
                    await self._fetch(f"{self.issuer}/.well-known/openid-configuration")
                )
            keys = self._parse(await self._fetch(self._jwks_uri))
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            log.warning(
                "could not load the issuer's signing keys; keeping %d cached",
                len(self._keys),
                extra={"error_type": type(exc).__name__},
            )
            return
        self._keys = keys

    def _jwks_uri_from(self, config: Mapping[str, Any]) -> str:
        issuer, jwks_uri = config.get("issuer"), config.get("jwks_uri")
        if not isinstance(issuer, str) or issuer.rstrip("/") != self.issuer:
            raise ValueError("the discovery document names another issuer")
        if not isinstance(jwks_uri, str) or not jwks_uri.startswith(("https://", "http://")):
            raise ValueError("the discovery document has no jwks_uri")
        if jwks_uri.startswith("http://") and self.issuer.startswith("https://"):
            raise ValueError("jwks_uri must use https for an https issuer")
        return jwks_uri

    @staticmethod
    def _parse(jwks: Mapping[str, Any]) -> dict[str, Any]:
        entries = jwks.get("keys")
        if not isinstance(entries, list):
            raise ValueError("the JWKS has no keys list")
        keys: dict[str, Any] = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("use", "sig") != "sig" or entry.get("kty") != "RSA":
                continue
            kid = entry.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            try:
                keys[kid] = jwt.PyJWK(entry, algorithm="RS256").key
            except jwt.PyJWTError:
                log.warning("skipping a signing key that could not be parsed", extra={"kid": kid})
        if not keys:
            raise ValueError("the JWKS has no usable RS256 signing keys")
        return keys
