"""Hash a password for the local password sign-in (LOGIN_PASSWORD_HASH in .env). Asks for it without echoing it and
prints only the hash; the password itself is never written anywhere.

    uv run python scripts/admin/hash_password.py
"""

from __future__ import annotations

import getpass
import sys

from sabha_api.auth.password import hash_password


def main() -> int:
    password = getpass.getpass("Password: ")
    if not password or password != getpass.getpass("Again: "):
        print("The two did not match (or were empty); nothing was made.", file=sys.stderr)
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
