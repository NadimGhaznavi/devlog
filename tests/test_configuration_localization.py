import json
from pathlib import Path

import pytest

from devlog.constants.DText import DText
from devlog.interface.Configuration import Configuration
from devlog.interface.Localizer import Localizer


ROOT = Path(__file__).parents[1]


def test_unchanged_canonical_templates_and_complete_catalogue():
    for component, filename in (("bmforge-db-server", "DbMgr.py"), ("bmforge-localization", "Localizer.py")):
        assert (ROOT / "devlog/interface" / filename).read_bytes() == (ROOT / ".agents/skills" / component / "assets" / filename).read_bytes()
    catalogue = json.loads((ROOT / "devlog/locales/en.json").read_text())
    assert set(catalogue) == {str(key) for key in DText}


def test_locale_override_quality_parent_fallback_and_placeholder_validation(tmp_path):
    (tmp_path / "en.json").write_text(json.dumps({"hello": "Hello {name}", "other": "Other"}))
    (tmp_path / "fr.json").write_text(json.dumps({"hello": "Bonjour {name}"}))
    (tmp_path / "zh-TW.json").write_text(json.dumps({"other": "測試"}))
    localizer = Localizer(tmp_path)
    assert localizer.select(explicit="fr-CA", accept_language="en") == "fr"
    assert localizer.select(accept_language="en;q=0.2,fr;q=0.9") == "fr"
    assert localizer.select(explicit="zh-CN") == "en"
    assert localizer.text("hello", locale="fr", name="Dan") == "Bonjour Dan"
    assert localizer.text("other", locale="fr") == "Other"
    with pytest.raises(KeyError):
        localizer.text("unknown")
    (tmp_path / "fr.json").write_text(json.dumps({"hello": "Bonjour {wrong}"}))
    with pytest.raises(ValueError, match="placeholders"):
        Localizer(tmp_path)


def test_listener_defaults_and_invalid_configuration(tmp_path):
    config = Configuration(ROOT / "conf/devlog.json")
    assert config.bindings == {"http": ("0.0.0.0", 19700), "zmq": ("0.0.0.0", 19701)}
    bad = tmp_path / "bad.json"
    for value in ({"http": {"port": True}}, {"zmq": {"port": 65536}}, {"http": {"interface": "invalid"}}, {"zmq": {"port": 19700}}):
        bad.write_text(json.dumps(value))
        with pytest.raises(ValueError):
            Configuration(bad)


def test_database_file_is_data_not_shell(tmp_path, monkeypatch):
    config = Configuration(ROOT / "conf/devlog.json")
    password = "$(touch /tmp/never-run-this); 'literal'"
    credentials = tmp_path / "database.env"
    credentials.write_text("DB_HOST=localhost\nDB_USER=devlog\nDB_NAME=devlog\nDB_PASSWORD=" + password + "\n")
    monkeypatch.setenv("DEVLOG_DATABASE_ENV", str(credentials))
    for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_SOCKET"):
        monkeypatch.delenv(key, raising=False)
    assert config.database()["password"] == password
