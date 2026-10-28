"""Password hashes for the local password sign-in (dev_idp.password_router): scrypt from the standard library.

Stored form: "scrypt$<n>$<r>$<p>$<salt, base64>$<key, base64>". Make one with scripts/admin/hash_password.py; the
password itself is never stored. Checking compares in constant time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P, KEY_BYTES = 2**15, 8, 1, 32
MAXMEM = 64 * 1024 * 1024  # scrypt needs 128 * n * r bytes (32 MiB here); OpenSSL's default limit is lower


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=KEY_BYTES, maxmem=MAXMEM)
    encode = base64.b64encode
    return f"scrypt${N}${R}${P}${encode(salt).decode()}${encode(key).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """True when `password` matches `stored`; False for a wrong password or a malformed hash."""
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(key)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected), maxmem=MAXMEM)  # fmt: skip
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
