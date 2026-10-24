"""DevLog's own packaging/release contract, independent of BMForge's changelog."""
import importlib.util
from pathlib import Path
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/new-release.sh"
CONSTANTS = ROOT / "devlog/constants/DDevLog.py"


def test_package_version_matches_literal_application_version():
    spec = importlib.util.spec_from_file_location("devlog_cmdb", ROOT / "scripts/check-cmdb.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    metadata = checker.validate(CONSTANTS.read_text(), "DevLog", "devlog/constants/DDevLog.py")
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert package["project"]["version"] == metadata["VERSION"]


def test_release_script_from_bmforge_updates_package_metadata_without_releasing():
    source = SCRIPT.read_text()
    assert 'readonly project_name="DevLog"' in source
    assert 'readonly version_file="devlog/constants/DDevLog.py"' in source
    assert 'package_metadata check "${value}"' in source
    assert 'package_metadata update "${previous_version}" "${version}"' in source
    assert 'git add -- pyproject.toml' in source
    syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    help_result = subprocess.run(["bash", str(SCRIPT), "--help"], cwd=ROOT,
                                 capture_output=True, text=True)
    assert help_result.returncode == 0, help_result.stderr
    assert "Likely next version" in help_result.stdout


def test_three_lifecycle_entry_points_and_optional_server_installer():
    for name in ("install.sh", "install-server.sh", "upgrade.sh", "uninstall.sh"):
        file = ROOT / "scripts" / name
        assert file.is_file()
        assert subprocess.run(["bash", "-n", str(file)], capture_output=True).returncode == 0
    code = (ROOT / "scripts/deploy.py").read_text()
    assert 'actions.add_parser("uninstall"' in code
    assert '"--check"' in code
    assert '".installation-manifest.json"' in code
    assert '".deployment-version"' in code
