#!/usr/bin/env python3
"""One-time helper: read the Yelp `datadome` cookie from your local Chrome
(Default profile), decrypt it with the Chrome Safe Storage key, and save it to
RWL_COOKIE_FILE. The collector injects it so its browser starts from your
already-verified session instead of a cold, challengeable one.

Only the single `datadome` cookie for yelp.com is read — not logins or history.
macOS will prompt once to allow Keychain access to "Chrome Safe Storage".
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

CHROME = Path.home() / "Library/Application Support/Google/Chrome"
PROFILE = os.environ.get("RWL_CHROME_PROFILE", "Default")
COOKIE_FILE = Path(os.environ.get("RWL_COOKIE_FILE", str(Path.home() / ".restowaitlist/datadome.json")))


def chrome_key() -> bytes:
    pw = subprocess.check_output(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"]
    ).strip()
    return hashlib.pbkdf2_hmac("sha1", pw, b"saltysalt", 1003, 16)


def decrypt(enc: bytes, key: bytes) -> str:
    if enc[:3] in (b"v10", b"v11"):
        enc = enc[3:]
    dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    out = dec.update(enc) + dec.finalize()
    pad = out[-1]
    if 1 <= pad <= 16:
        out = out[:-pad]
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        # Chrome >= v130 prepends a 32-byte SHA256 domain hash.
        return out[32:].decode("utf-8", "replace")


def main() -> int:
    src = CHROME / PROFILE / "Cookies"
    if not src.exists():
        src = CHROME / PROFILE / "Network" / "Cookies"
    if not src.exists():
        print(f"No Cookies DB under {CHROME / PROFILE}")
        return 2

    key = chrome_key()
    with tempfile.TemporaryDirectory() as tmp:
        dbcopy = Path(tmp) / "Cookies"
        shutil.copy(src, dbcopy)
        con = sqlite3.connect(str(dbcopy))
        rows = con.execute(
            "SELECT host_key,name,encrypted_value,path,is_secure,is_httponly,expires_utc "
            "FROM cookies WHERE host_key LIKE '%yelp.com' AND name='datadome'"
        ).fetchall()
        con.close()

    if not rows:
        print("No yelp.com datadome cookie found. Open the Yelp waitlist page in Chrome first.")
        return 1

    host, name, enc, path, secure, httponly, expires_utc = rows[0]
    value = decrypt(enc, key)
    expires = (expires_utc / 1_000_000) - 11_644_473_600 if expires_utc else -1
    cookie = {
        "name": name,
        "value": value,
        "domain": host if host.startswith(".") else "." + host.lstrip("."),
        "path": path or "/",
        "secure": bool(secure),
        "httpOnly": bool(httponly),
        "expires": expires,
    }
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(cookie))
    print(f"Saved datadome cookie ({len(value)} chars, domain {cookie['domain']}) -> {COOKIE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
