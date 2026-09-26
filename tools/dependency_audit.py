"""
Known-vulnerability audit of every installed Python package (direct AND transitive) against OSV.dev.

    python tools/dependency_audit.py        # exit 1 if any installed version has a known vulnerability

Part of the weekly audit (interim plan, priority B). Sends only package names and versions -- public
information -- to OSV's batch API; changes nothing. The direct dependencies are pinned exactly in
requirements.txt; the transitive ones are resolved fresh on every GitHub runner, so this audits the local
environment as the closest available copy and says so. First run 2026-09-26: 43 packages, 0 known.
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"


def installed() -> list[tuple[str, str]]:
    out = subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"], capture_output=True, text=True, check=True).stdout
    return [tuple(line.split("==", 1)) for line in out.split() if "==" in line]


def direct_names(requirements: Path = Path("requirements.txt")) -> set[str]:
    return {line.split("==")[0].split("[")[0].strip().lower() for line in requirements.read_text(encoding="utf-8").splitlines()
            if "==" in line and not line.lstrip().startswith("#")}


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                              "User-Agent": "bitcoin-agent-audit"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _get(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "bitcoin-agent-audit"}), timeout=30) as r:
        return json.load(r)


def findings(pkgs: list[tuple[str, str]], batch_results: list[dict]) -> list[dict]:
    """Pure: pair each package with OSV's answer; keep the ones that have vulnerabilities."""
    return [{"package": n, "version": v, "ids": [x["id"] for x in res.get("vulns", [])]}
            for (n, v), res in zip(pkgs, batch_results) if res.get("vulns")]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pkgs, direct = installed(), direct_names()
    results = _post(OSV_BATCH, {"queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in pkgs]})["results"]
    hits = findings(pkgs, results)
    print(f"{len(pkgs)} installed packages checked ({len(direct)} direct, pinned); "
          f"{len(hits)} with a known vulnerability")
    for h in hits:
        kind = "DIRECT" if h["package"].lower() in direct else "transitive"
        print(f"  {h['package']}=={h['version']} [{kind}]")
        for vid in h["ids"][:8]:
            d = _get(OSV_VULN + vid)
            fixed = sorted({e["fixed"] for a in d.get("affected", []) if a.get("package", {}).get("name", "").lower() == h["package"].lower()
                            for rg in a.get("ranges", []) for e in rg.get("events", []) if "fixed" in e})
            print(f"     {vid}: {d.get('summary', '')[:110]} | fixed in {', '.join(fixed) or '?'}")
    if hits:
        print("Any upgrade is a deliberate commit, re-verified by the golden scoring test, the feature fingerprint and parity.")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
