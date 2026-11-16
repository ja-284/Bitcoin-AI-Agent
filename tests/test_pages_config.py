"""
Papirsidens publisering (eierens godkjenning 2026-11-16): tools/pages_config.py og .github/workflows/pages.yml.
Siden er offentlig, så bare offentlige verdier kan havne i den: en hemmelig nøkkel eller en service_role-nøkkel nektes,
nøkkelen skrives aldri ut, innstillingsfilen kan aldri committes, den oppdiktede demoen publiseres ikke, og jobben har
ingen hemmelighet og ingen databasetilkobling.
"""

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("tools").resolve()))
import pages_config as C  # noqa: E402

URL = "https://abcdefghijklmnopqrst.supabase.co"
PUBLISHABLE = "sb_publishable_TESTONLY_abcdefghij"


def _jwt(role: str) -> str:  # built at run time: no token-shaped string is committed
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'HS256'})}.{enc({'role': role, 'iss': 'test'})}.signature"


def test_only_a_public_key_is_accepted():
    assert C.check_key(PUBLISHABLE) == PUBLISHABLE
    assert C.check_key(_jwt("anon")) == _jwt("anon")
    for bad in ("sb_secret_TESTONLY_abcdefghij", _jwt("service_role"), _jwt("authenticated"), "", "not-a-key", "a.b.c"):
        with pytest.raises(C.ConfigError):
            C.check_key(bad)


def test_the_url_must_be_a_project_address():
    assert C.check_url(URL + "/") == URL
    for bad in ("http://abcdefghijklmnopqrst.supabase.co", "https://evil.example.com", "https://abc.supabase.co", ""):
        with pytest.raises(C.ConfigError):
            C.check_url(bad)


def test_the_file_holds_the_two_public_values_and_nothing_else():
    text = C.render(URL, PUBLISHABLE)
    assert re.findall(r"export const (\w+) = ", text) == ["SUPABASE_URL", "SUPABASE_KEY"]
    assert json.dumps(URL) in text and json.dumps(PUBLISHABLE) in text


def test_a_refused_key_is_never_printed(tmp_path):
    secret = "sb_secret_TESTONLY_doNotPrintThis123"
    out = tmp_path / "config.js"
    r = subprocess.run([sys.executable, "tools/pages_config.py", str(out)], capture_output=True, text=True, encoding="utf-8",
                       env={"SUPABASE_URL": URL, "SUPABASE_PUBLISHABLE_KEY": secret, "SYSTEMROOT": "C:\\Windows", "PATH": "",
                            "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 1 and not out.exists()
    assert secret not in r.stdout + r.stderr and "HEMMELIG" in r.stdout


def test_the_settings_file_is_never_committed():
    assert "web/papir/config.js" in Path(".gitignore").read_text(encoding="utf-8").splitlines()
    tracked = subprocess.run(["git", "ls-files", "web/papir"], capture_output=True, text=True).stdout.split()
    assert "web/papir/config.js" not in tracked


def test_the_workflow_publishes_only_the_page_with_public_settings_and_no_secret():
    wf = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "secrets." not in wf and "DATABASE_URL" not in wf  # no secret and no database in this job
    assert "python3 tools/pages_config.py web/papir/config.js" in wf
    assert "rm web/papir/demo.json" in wf  # the fictional demo is not published
    assert re.search(r"upload-pages-artifact@[0-9a-f]{40}[^\n]*\n\s+with:\n\s+path: web/papir\n", wf)
    perms = re.search(r"\npermissions:\n((?:  .+\n)+)", wf).group(1)
    assert [ln.split(":")[0].strip() for ln in perms.splitlines()] == ["contents", "pages", "id-token"]
    assert "contents: read" in perms
    assert "if: ${{ vars.SUPABASE_URL != '' }}" in wf  # skipped, not failed, until the owner adds the settings
