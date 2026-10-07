"""Release safety checks use synthetic credentials and mock provider boundaries."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dh_compass.preprocessing import geocoding
from dh_compass.reporting.viewer_export import save_viewer_data


def test_viewer_never_copies_server_credentials(monkeypatch, tmp_path):
    secret = "synthetic-private-server-value"
    monkeypatch.setenv("CARTO_API_KEY", secret)
    monkeypatch.setenv("carto_api", secret)
    template = tmp_path / "template.html"
    template.write_text('<body>__CARTO_API_KEY__</body>', encoding="utf-8")
    output = tmp_path / "viewer.json"
    save_viewer_data({"edges": {"type": "FeatureCollection", "features": []}}, output, template_path=template)
    assert secret not in output.with_suffix(".html").read_text(encoding="utf-8")
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["edges"]["source_provenance"]["database_license"] == "ODbL-1.0"


def test_geocoding_caches_and_identifies_requests(monkeypatch, tmp_path):
    calls = []
    payload = {"features": []}
    def get(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(geocoding.requests, "get", get)
    monkeypatch.setattr(geocoding, "_last_request", 0)
    for _ in range(2):
        assert geocoding.search_location("test", endpoint="https://example.invalid/search", cache_root=tmp_path) == payload
    assert len(calls) == 1
    assert calls[0]["headers"]["User-Agent"].startswith("DH-COMPASS/")
    with pytest.raises(ValueError, match="Configure"):
        geocoding.search_location("test", endpoint="", cache_root=tmp_path)


def test_repository_entry_denylist_and_redaction(monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts" / "release_audit.py"
    monkeypatch.syspath_prepend(str(script.parent))
    spec = importlib.util.spec_from_file_location("release_audit", script)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    assert audit.inspect_entry("data/reference/EEX Phelix-DE Baseload Cal-2022.xlsx", b"")
    assert audit.inspect_entry(".cdsapirc", b"")
    assert audit.inspect_entry("data/external/KWW_Waermekatalog.xlsx", b"")
    assert audit.inspect_entry("data/external/Warmebedarf_NRW.gdb/a000.gdbtable", b"")
    token = ("ghp" + "_" + "x" * 40).encode()
    findings = audit.inspect_entry("settings.py", token)
    assert findings
    assert token.decode() not in " ".join(findings)
    assert not audit.inspect_entry("src/app.py", b"print('hello')")
    assert not audit.inspect_entry("data/reference/slp_parameters.json", b"{}")
    assert audit.inspect_entry("data/reference/private-slp.json", b"{}")
