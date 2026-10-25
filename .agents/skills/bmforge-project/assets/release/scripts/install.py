#!/usr/bin/env python3
"""Source-file deployment baseline; configure project-specific work before use."""

import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile


BMFORGE_COMPONENT = {"id": "bmforge.installation", "spec_version": "0.1.1"}

PROJECT_NAME = "__PROJECT_NAME__"
# Turn this on only after implementing the project's full deployment contract.
DEPLOYMENT_READY = False
COPY_TREES = ("__PROJECT_SLUG__", "scripts")
COPY_FILES = ()
MANIFEST = ".installation-manifest.json"
VERSION_MARKER = ".deployment-version"


def relative_path(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Managed paths must be strings")
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or path.as_posix() != name or name == '.':
        raise ValueError(f"Invalid managed path: {name}")
    if name in (MANIFEST, VERSION_MARKER):
        raise ValueError(f"Reserved bookkeeping path: {name}")
    return name


def reject_symlinks(path: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise ValueError(f"Refusing a symbolic link in deployment path: {candidate}")


class Installation:
    def __init__(self, checkout: Path, *, destination: Path | None = None) -> None:
        self.checkout = checkout.resolve()
        self.version_file = f"{PROJECT_NAME.lower()}/constants/D{PROJECT_NAME}.py"
        spec = importlib.util.spec_from_file_location('cmdb_checker', self.checkout / 'scripts/check-cmdb.py')
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.metadata = checker.validate((self.checkout / self.version_file).read_text(),
                                         PROJECT_NAME, self.version_file)
        self.destination = Path(destination if destination is not None else self.metadata['BASE_DIR']).absolute()
        reject_symlinks(self.destination)
        if (self.checkout.is_relative_to(self.destination)
                or self.destination.is_relative_to(self.checkout)):
            raise ValueError("Run deployment from a separate checkout outside the installation")

    def installed_files(self) -> list[str] | None:
        manifest = self.destination / MANIFEST
        reject_symlinks(manifest)
        if not manifest.exists():
            if self.destination.exists():
                raise ValueError("Installation directory exists without an ownership manifest; inspect it before proceeding")
            return None
        data = json.loads(manifest.read_text())
        if (not isinstance(data, dict) or data.get('project') != PROJECT_NAME
                or not isinstance(data.get('files'), list)):
            raise ValueError("Installation ownership manifest does not match this project")
        names = [relative_path(name) for name in data['files']]
        if (len(names) != len(set(names))
                or self.version_file not in names and not (not names and data.get('removed') is True)):
            raise ValueError("Installation ownership manifest has invalid files")
        for name in [*names, VERSION_MARKER]:
            path = self.destination / name
            reject_symlinks(path)
            if path.exists() and not path.is_file():
                raise ValueError(f"Managed file is no longer a regular file: {path}")
        return names

    def source_files(self) -> list[str]:
        names = {relative_path(name) for name in COPY_FILES}
        for name in COPY_TREES:
            folder = self.checkout / relative_path(name)
            reject_symlinks(folder)
            if not folder.is_dir():
                raise ValueError(f"Missing source directory: {name}")
            for path in folder.rglob('*'):
                if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):
                    continue
                reject_symlinks(path)
                if path.is_file():
                    names.add(relative_path(path.relative_to(self.checkout).as_posix()))
        if self.version_file not in names:
            raise ValueError("Deployment must include readable CMDB constants")
        for name in names:
            source = self.checkout / name
            reject_symlinks(source)
            if not source.is_file():
                raise ValueError(f"Missing source file: {name}")
            target = self.destination / name
            reject_symlinks(target)
            if target.exists() and not target.is_file():
                raise ValueError(f"Managed file target is not a regular file: {target}")
        return sorted(names)

    def plan(self, action: str) -> tuple[list[str] | None, list[str]]:
        if not DEPLOYMENT_READY:
            raise ValueError("Deployment is not configured: implement provisioning, lifecycle, and health checks before enabling it")
        previous = self.installed_files()
        if action == 'upgrade' and not previous:
            raise ValueError("No installation found; run install.sh first")
        current = [] if action == 'uninstall' else self.source_files()
        if previous is not None:
            for name in set(current) - set(previous):
                if (self.destination / name).exists():
                    raise ValueError(f"New managed file would overwrite an unowned file: {name}")
        return previous, current

    def atomic_write(self, path: Path, content: bytes, mode: int = 0o644) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        for directory in (path.parent, *path.parent.parents):
            if directory == self.destination.parent:
                break
            directory.chmod(0o755)
        descriptor, name = tempfile.mkstemp(prefix='.bmforge-install-', dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content)
                os.fchmod(stream.fileno(), mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def remove_files(self, names: list[str]) -> None:
        for name in names:
            path = self.destination / name
            path.unlink(missing_ok=True)
            for directory in path.parents:
                if directory == self.destination:
                    break
                try:
                    directory.rmdir()
                except OSError:
                    break

    def apply(self, action: str, *, check: bool = False) -> None:
        previous, names = self.plan(action)
        if check:
            print(f"{action}: checks passed for {self.destination}; no files changed.")
            return
        if action == 'uninstall':
            if previous is not None:
                self.remove_files(previous)
                (self.destination / VERSION_MARKER).unlink(missing_ok=True)
                (self.destination / MANIFEST).unlink()
                try:
                    self.destination.rmdir()
                except OSError:
                    # Remember that retained state belongs to this project so
                    # repeated removal or reinstallation can recognize it.
                    removed = {'project': PROJECT_NAME, 'files': [], 'removed': True}
                    self.atomic_write(self.destination / MANIFEST, (json.dumps(removed, indent=2) + '\n').encode())
            print(f"Removed managed {PROJECT_NAME} files; unowned files and persistent data are retained.")
            return
        self.destination.mkdir(parents=True, exist_ok=True)
        self.destination.chmod(0o755)
        # Keep ownership information for partial copies so a retry or uninstall can
        # account for new files. Advance the successful-version marker only last.
        owned = sorted(set(previous or ()) | set(names))
        ownership = {'project': PROJECT_NAME, 'files': owned}
        self.atomic_write(self.destination / MANIFEST, (json.dumps(ownership, indent=2) + '\n').encode())
        # Existing managed files may change before success; this is not rollback.
        for name in [item for item in names if item != self.version_file]:
            source = self.checkout / name
            mode = 0o755 if source.stat().st_mode & 0o111 else 0o644
            self.atomic_write(self.destination / name, source.read_bytes(), mode)
        self.remove_files(sorted(set(previous or ()) - set(names)))
        self.atomic_write(self.destination / self.version_file, (self.checkout / self.version_file).read_bytes())
        ownership['files'] = names
        self.atomic_write(self.destination / MANIFEST, (json.dumps(ownership, indent=2) + '\n').encode())
        self.atomic_write(self.destination / VERSION_MARKER, (self.metadata['VERSION'] + '\n').encode())
        print(f"{action}: {PROJECT_NAME} {self.metadata['VERSION']} deployed to {self.destination}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'upgrade', 'uninstall'))
    parser.add_argument('--check', action='store_true', help='Validate the operation without changing files')
    args = parser.parse_args()
    if not args.check and os.geteuid() != 0:
        parser.error('Run deployment as root; --check and --help do not require root')
    try:
        Installation(Path(__file__).resolve().parents[1]).apply(args.action, check=args.check)
    except (OSError, ValueError, TypeError, SyntaxError) as error:
        parser.exit(1, f"Deployment failed: {error}\n")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
