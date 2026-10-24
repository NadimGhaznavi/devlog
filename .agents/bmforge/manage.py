#!/usr/bin/env python3
"""Install pinned BMForge Codex skills into a new application repository.

The check operation never writes to the application or its installed skills.
"""

from argparse import ArgumentParser
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SOURCE_URL = "https://github.com/NadimGhaznavi/bmforge.git"
SOURCE_BRANCH = "main"
SKILLS = {
    "bmforge-project": (None, ()),
    "bmforge-constants": ("pages/component-constants.md", (
        "components/reference/snake-lab/snakelab/constants/DGame.py",
        "components/reference/snake-lab/snakelab/constants/DSQL.py",
        "components/reference/snake-lab/snakelab/constants/DMyLog.py",
        "components/reference/snake-lab/snakelab/constants/DSnakeLab.py",
        "components/reference/bmgeoip/bmgeoip/constants/DBMGeoIP.py",
        "components/reference/bmgeoip/bmgeoip/constants/DGeoIp.py",
        "components/reference/bmgeoip/bmgeoip/constants/DZMQ.py",
    )),
    "bmforge-localization": ("pages/component-localization.md", (
        "components/reference/minimal-mistakes/_includes/language-selector.html",
        "components/reference/minimal-mistakes/assets/js/multilingual.js",
        "components/reference/blog/_data/taxonomy_translations.yml",
        "components/reference/blog/es/index.md",
    )),
    "bmforge-http": ("pages/component-http.md", (
        "components/reference/bmgeoip/bmgeoip/server/BMGeoIPServer.py",
        "components/reference/bmgeoip/bmgeoip/server/BMGeoIPHandler.py",
        "components/reference/bmgeoip/bmgeoip/server/LookupHandler.py",
    )),
    "bmforge-zmq": ("pages/component-zmq.md", (
        "components/reference/bmgeoip/bmgeoip/zmq/ZMQServer.py",
        "components/reference/bmgeoip/bmgeoip/zmq/ZMQMsg.py",
    )),
    "bmforge-db-server": ("pages/component-db-server.md", (
        "components/reference/bmgeoip/bmgeoip/interface/GeoIpDb.py",
        "components/reference/mycount/mycount/interface/VisitDb.py",
    )),
    "bmforge-git": ("pages/component-git.md", (
        "components/reference/snake-web-code/snakewebcode/interface/GitPublisher.py",
    )),
    "bmforge-visualization": ("pages/component-visualization.md", (
        "components/reference/mycount/mycount/server/ControlPages.py",
        "components/reference/mycount/mycount/server/templates/base.html",
        "components/reference/mycount/mycount/server/templates/chart_theme.html",
        "components/reference/mycount/mycount/server/templates/all_traffic.html",
        "components/reference/mycount/mycount/server/templates/pie_charts.html",
        "components/reference/mycount/mycount/server/templates/marketing_chart.html",
        "components/reference/mycount/mycount/server/templates/visitor_map.html",
        "components/reference/cmdb/cmdb/server/templates/home.html",
        "components/reference/cmdb/cmdb/server/static/machines.js",
        "components/reference/cmdb/cmdb/server/static/vendor/cytoscape-3.34.3.min.js",
        "components/reference/cmdb/cmdb/server/static/vendor/cytoscape-LICENSE",
    )),
}
BASE_SKILLS = ("bmforge-project", "bmforge-constants", "bmforge-localization")
COMMON = (
    "pages/engineering-contract.md",
    "pages/classification.md",
    "pages/specification-lifecycle.md",
    "pages/component-blueprints.md",
)
HEALTH = "pages/health-checks.md"
DB_TEMPLATE = "components/templates/db-server/interface/DbMgr.py"
GIT_TEMPLATE = "components/templates/git/Git.py"
CONSTANTS_TEMPLATE = "templates/project/constants/DProject.py"
LOCALIZER_TEMPLATE = "components/templates/localization/interface/Localizer.py"
TEXT_TEMPLATE = "components/templates/constants/DText.py"
EN_CATALOG = "components/templates/localization/locales/en.json"
LOCK = Path(".agents/bmforge/lock.json")
MANAGER = Path(".agents/bmforge/manage.py")


class SetupError(Exception):
    """A safe, user-facing failure."""


def git(*args, cwd=None):
    result = subprocess.run(["git", *map(str, args)], cwd=cwd,
                            capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise SetupError(f"Git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


@contextmanager
def source_checkout(source):
    """Use an explicit checkout or an ephemeral clone of the published branch."""
    if source and Path(source).is_dir():
        root = Path(source).resolve()
        if not (root / "skills/bmforge-project/SKILL.md").is_file():
            raise SetupError(f"Not a BMForge skill source: {root}")
        yield root, git("rev-parse", "HEAD", cwd=root)
        return
    with tempfile.TemporaryDirectory(prefix="bmforge-source-") as directory:
        remote = source or SOURCE_URL
        git("clone", "--quiet", "--depth", "1", "--branch", SOURCE_BRANCH,
            "--", remote, directory)
        root = Path(directory)
        yield root, git("rev-parse", "HEAD", cwd=root)


def project_root(project):
    root = Path(project).resolve()
    if not root.is_dir():
        raise SetupError(f"Project directory does not exist: {root}")
    actual = Path(git("rev-parse", "--show-toplevel", cwd=root)).resolve()
    if root != actual:
        raise SetupError("Run against the repository root, not a nested directory")
    return root


def selected_names(value):
    names = [p.strip() for p in value.split(",") if p.strip()] if value else []
    if len(names) != len(set(names)):
        raise SetupError("Duplicate component selection")
    unknown = sorted(set(names) - (set(SKILLS) - set(BASE_SKILLS)))
    if unknown:
        raise SetupError("Unknown component(s): " + ", ".join(unknown))
    return names


def bundle(source, name):
    spec, snapshots = SKILLS[name]
    files = {"SKILL.md": f"skills/{name}/SKILL.md"}
    for common in COMMON:
        files["references/" + Path(common).name] = common
    if spec:
        files["references/specification.md"] = spec
    if name in ("bmforge-http", "bmforge-zmq", "bmforge-db-server"):
        files["references/health-checks.md"] = HEALTH
    for snapshot in snapshots:
        files["references/source/" + snapshot.removeprefix("components/reference/")] = snapshot
    if name == "bmforge-db-server":
        files["assets/DbMgr.py"] = DB_TEMPLATE
    if name == "bmforge-git":
        files["assets/Git.py"] = GIT_TEMPLATE
    if name == "bmforge-constants":
        files["assets/DProject.py"] = CONSTANTS_TEMPLATE
    if name == "bmforge-localization":
        files["assets/Localizer.py"] = LOCALIZER_TEMPLATE
        files["assets/DText.py"] = TEXT_TEMPLATE
        files["assets/en.json"] = EN_CATALOG
    result = {}
    for destination, original in files.items():
        path = source / original
        if not path.is_file() or path.is_symlink():
            raise SetupError(f"Missing regular BMForge source file: {original}")
        result[destination] = path.read_bytes()
    return result


def fingerprint(files):
    digest = sha256()
    for name, data in sorted(files.items()):
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(sha256(data).digest())
    return digest.hexdigest()


def installed_bundle(directory):
    if not directory.is_dir() or directory.is_symlink():
        raise SetupError(f"Missing or invalid installed skill: {directory}")
    entries = {}
    for file in directory.rglob("*"):
        if file.is_symlink():
            raise SetupError(f"Symlinks are not permitted in installed skills: {file}")
        if file.is_file():
            entries[file.relative_to(directory).as_posix()] = file.read_bytes()
    return entries


def spec_version(source, name):
    spec, _ = SKILLS[name]
    if spec is None:
        return "0.1.0"
    for line in (source / spec).read_text().splitlines():
        if line.startswith("spec_version: "):
            return line.split('"')[1]
    raise SetupError(f"Specification version missing for {name}")


def copy_bundle(directory, files):
    directory.mkdir(parents=True, exist_ok=False)
    for relative, content in files.items():
        output = directory / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)


def write_json_atomic(path, value):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".bmforge-", delete=False) as stream:
        candidate = Path(stream.name)
        try:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            candidate.replace(path)
        finally:
            candidate.unlink(missing_ok=True)


def root_agents():
    return """# Project engineering instructions

This project uses **pinned BMForge Codex skills**. These are project-owned copies,
not live imports from BMForge or another application.

Before the first BMForge-related edit in a Codex session, run the **read-only**
update check from the repository root:

    python3 .agents/bmforge/manage.py check --project .

Report available changes or an unavailable check to the user. **Do not apply
updates**, reinstall skills, or replace approved technologies without explicit
user authorization. Continue using the pinned skills unless instructed otherwise.

Read `.agents/skills/bmforge-project/SKILL.md` for architecture. Every new app
also follows the pinned `bmforge-constants` and `bmforge-localization` skills:
centralize stable programmatic identifiers and prepare English localization keys
from its first user-facing feature. Add real translations only when provided or
requested, never by guessing. Invoke other component skills as needed.
Follow each selected skill's local
`references/specification.md` and approved module inventory. Never invent another
framework, database driver or plotting library as a shortcut.

Component selection and application-specific behaviour belong to this project's
requirements. A pinned skill is an instruction bundle, not executable app code.
"""


def start_init(args):
    root = project_root(args.project)
    if (root / ".agents").exists() or (root / "AGENTS.md").exists():
        raise SetupError("Refusing to overwrite existing .agents/ or AGENTS.md")
    names = [*BASE_SKILLS, *selected_names(args.components)]
    with source_checkout(args.source) as (source, revision):
        bundles = {name: bundle(source, name) for name in names}
        versions = {name: spec_version(source, name) for name in names}
        manager_source = (source / "skills/bmforge-new-project/scripts/manage.py").read_bytes()
    base = root / ".agents"
    try:
        (root / LOCK.parent).mkdir(parents=True)
        (root / MANAGER).write_bytes(manager_source)
        for name, files in bundles.items():
            copy_bundle(root / ".agents/skills" / name, files)
        write_json_atomic(root / LOCK, {
            "schema": 1,
            "repository": args.source or SOURCE_URL,
            "branch": SOURCE_BRANCH,
            "source_commit": revision,
            "manager_sha256": sha256(manager_source).hexdigest(),
            "skills": {name: {"spec_version": versions[name],
                               "sha256": fingerprint(files),
                               "source_commit": revision}
                       for name, files in bundles.items()},
        })
        (root / "AGENTS.md").write_text(root_agents(), encoding="utf-8")
    except BaseException:
        if base.exists():
            shutil.rmtree(base)
        raise
    print(f"Installed {len(names)} pinned BMForge skill(s) from {revision[:12]}:")
    for name in names:
        print(f"  {name} ({versions[name]})")
    print("No application code was generated. Check updates with:")
    print("  python3 .agents/bmforge/manage.py check --project .")


def load_lock(root):
    try:
        value = json.loads((root / LOCK).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SetupError(f"Missing or invalid BMForge lock: {error}") from error
    if value.get("schema") != 1 or not isinstance(value.get("skills"), dict):
        raise SetupError("Unsupported BMForge lock format")
    if not (root / MANAGER).is_file():
        raise SetupError("Project-local BMForge manager is missing")
    return value


def start_add(args):
    root = project_root(args.project)
    lock = load_lock(root)
    names = selected_names(args.components)
    if not names:
        raise SetupError("Select at least one additional component")
    present = sorted(set(names) & set(lock["skills"]))
    if present:
        raise SetupError("Already installed, will not overwrite: " + ", ".join(present))
    for name in names:
        if (root / ".agents/skills" / name).exists():
            raise SetupError(f"Untracked local skill path exists: {name}")
    with source_checkout(args.source or lock["repository"]) as (source, revision):
        bundles = {name: bundle(source, name) for name in names}
        versions = {name: spec_version(source, name) for name in names}
    created = []
    try:
        for name, files in bundles.items():
            target = root / ".agents/skills" / name
            copy_bundle(target, files)
            created.append(target)
        for name, files in bundles.items():
            lock["skills"][name] = {"sha256": fingerprint(files),
                                    "spec_version": versions[name],
                                    "source_commit": revision}
        # Each component's local fingerprint is authoritative even when added later.
        write_json_atomic(root / LOCK, lock)
    except BaseException:
        for path in created:
            shutil.rmtree(path)
        raise
    for name in names:
        print(f"ADDED {name} ({versions[name]}) at source revision {revision[:12]}")
    print("Existing installed skills were not modified.")


def start_check(args):
    root = project_root(args.project)
    lock = load_lock(root)
    modified = []
    for name, installed in sorted(lock["skills"].items()):
        directory = root / ".agents/skills" / name
        try:
            current = fingerprint(installed_bundle(directory))
            if current != installed["sha256"]:
                modified.append(name)
        except (OSError, SetupError):
            modified.append(name)
    manager_changed = sha256((root / MANAGER).read_bytes()).hexdigest() != lock["manager_sha256"]
    for name in modified:
        print(f"LOCALLY MODIFIED {name}: installed snapshot differs from the lock; nothing changed")
    if manager_changed:
        print("LOCALLY MODIFIED manager: pinned update-check script differs from the lock")
    try:
        with source_checkout(args.source or lock["repository"]) as (source, revision):
            available = []
            for name, installed in sorted(lock["skills"].items()):
                new = bundle(source, name)
                if fingerprint(new) != installed["sha256"]:
                    new_version = spec_version(source, name)
                    available.append(name)
                    print(f"UPDATE AVAILABLE {name}: installed {installed['spec_version']}, "
                          f"available {new_version} ({revision[:12]})")
                elif name not in modified:
                    print(f"CURRENT {name}: {installed['spec_version']}")
            script = (source / "skills/bmforge-new-project/scripts/manage.py").read_bytes()
            if sha256(script).hexdigest() != lock["manager_sha256"]:
                available.append("manager")
                print(f"UPDATE AVAILABLE manager: available in {revision[:12]}")
    except (SetupError, OSError, subprocess.TimeoutExpired) as error:
        print(f"UPDATE CHECK UNAVAILABLE: {error}; installed skills were not changed", file=sys.stderr)
        return 2
    if available:
        print("User approval required for any upgrade. No updates were applied.")
    elif not modified and not manager_changed:
        print("All pinned BMForge skills are current. No files were changed.")
    return 1 if modified or manager_changed else 0


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("init", "add", "check"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--project", default=".", help="Existing Git repository root")
        cmd.add_argument("--source", help="BMForge checkout or Git remote (default: published main)")
        if action != "check":
            cmd.add_argument("--components", default="", help="Comma-separated component skill names")
    args = parser.parse_args(argv)
    try:
        return {"init": start_init, "add": start_add, "check": start_check}[args.action](args) or 0
    except (SetupError, OSError, subprocess.TimeoutExpired) as error:
        print(f"BMForge: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
