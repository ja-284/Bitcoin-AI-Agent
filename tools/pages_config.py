"""
Skriver papirsidens offentlige innstillinger (web/papir/config.js) når siden publiseres på GitHub Pages
(.github/workflows/pages.yml), fra repository-innstillingene SUPABASE_URL og SUPABASE_PUBLISHABLE_KEY. Filen blir
aldri committet (.gitignore).

Siden er offentlig, så alt i filen er offentlig. Derfor nekter verktøyet alt som ikke er en OFFENTLIG nøkkel: en
hemmelig nøkkel (sb_secret_…) eller en eldre service_role-nøkkel ville gått forbi alle reglene i databasen. Den
offentlige nøkkelen gir i seg selv ingen tilgang: `anon` har ingen rettigheter, og dokumentet kan bare leses av
Control Center-kontoen med to trinn (docs/api/stats_access.md). Nøkkelen skrives aldri ut, heller ikke i en feil.

    python tools/pages_config.py web/papir/config.js
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys

URL_RE = re.compile(r"https://[a-z0-9]{20}\.supabase\.co")


class ConfigError(ValueError):
    pass


def check_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not URL_RE.fullmatch(url):
        raise ConfigError("SUPABASE_URL må være prosjektets adresse, https://<20 tegn>.supabase.co")
    return url


def _jwt_role(key: str) -> str | None:
    parts = key.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("role")
    except (ValueError, json.JSONDecodeError, AttributeError):
        return None


def check_key(key: str) -> str:
    key = (key or "").strip()
    if key.startswith("sb_secret_"):
        raise ConfigError("dette er en HEMMELIG nøkkel (sb_secret_…); siden er offentlig og skal bare ha den offentlige")
    if key.startswith("sb_publishable_"):
        if not re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{10,}", key):
            raise ConfigError("den offentlige nøkkelen ser ikke riktig ut")
        return key
    role = _jwt_role(key)
    if role == "anon":
        return key
    if role is not None:
        raise ConfigError(f"denne nøkkelen har rollen «{role}»; siden skal bare ha den offentlige (anon)")
    raise ConfigError("SUPABASE_PUBLISHABLE_KEY må være prosjektets offentlige nøkkel (sb_publishable_… eller anon)")


def render(url: str, key: str) -> str:
    return ("// Laget ved publisering av tools/pages_config.py; aldri committet. Bare offentlige verdier.\n"
            f"export const SUPABASE_URL = {json.dumps(check_url(url))};\n"
            f"export const SUPABASE_KEY = {json.dumps(check_key(key))};\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("bruk: python tools/pages_config.py <utfil>")
        return 2
    try:
        text = render(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""))
    except ConfigError as e:
        print(f"publiserer ikke: {e}")
        return 1
    with open(argv[0], "w", encoding="utf-8") as f:
        f.write(text)
    print(f"skrev {argv[0]} (adresse og offentlig nøkkel; nøkkelen vises ikke her)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
