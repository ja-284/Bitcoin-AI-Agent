"""tools/dependency_audit.py: pairs packages with OSV's answers correctly, and reads requirements.txt right. No network."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("dependency_audit", Path("tools/dependency_audit.py"))
da = importlib.util.module_from_spec(spec)
spec.loader.exec_module(da)


def test_only_packages_with_vulnerabilities_are_reported_with_their_ids():
    pkgs = [("requests", "2.0.0"), ("numpy", "2.5.3"), ("urllib3", "1.0")]
    results = [{"vulns": [{"id": "GHSA-a"}, {"id": "PYSEC-b"}]}, {}, {"vulns": [{"id": "GHSA-c"}]}]
    assert da.findings(pkgs, results) == [{"package": "requests", "version": "2.0.0", "ids": ["GHSA-a", "PYSEC-b"]},
                                          {"package": "urllib3", "version": "1.0", "ids": ["GHSA-c"]}]
    assert da.findings(pkgs, [{}, {}, {}]) == []


def test_the_direct_dependencies_are_read_from_requirements(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("# comment == not a package\nrequests==2.34.2\npsycopg[binary]==3.3.6\n", encoding="utf-8")
    assert da.direct_names(req) == {"requests", "psycopg"}
    assert {"requests", "pandas", "numpy", "anthropic", "psycopg"} <= da.direct_names()
