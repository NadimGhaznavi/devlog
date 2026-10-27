---
title: Installation Lifecycle Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.installation"
spec_version: "0.1.1"
spec_status: "draft"
translation_key: bmforge-component-installation
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

## Purpose and scope

**Every BMForge application or reusable library must be installable, upgradeable and uninstallable.** This is a greenfield **baseline skill**, independent of whether the project has an HTTP server, database, systemd service or merely a command-line client or library. The global bootstrap lays down the *existing*, deployment-disabled BMForge installer templates; Codex must complete the actual lifecycle **after** the application's artifacts and requested installation topology are known, and **before** declaring the application release-ready.

Use [Installation Scripts]({{ site.baseurl }}{% link pages/installation-scripts.md %}) and [CMDB Compliance]({{ site.baseurl }}{% link pages/cmdb-compliance.md %}) as companion contracts. Publishing Git tags with `new-release.sh` is not installing a release.

## Approved implementation technology

Keep the existing source-file `templates/project/scripts/install.py` and its thin Bash wrappers for a simple source-only, library or CLI installation. Its complete reusable infrastructure imports are fixed:

| Origin | Python module | Purpose |
| --- | --- | --- |
| stdlib | `argparse` | Commands, `--help`, `--check` and validation |
| stdlib | `importlib.util` | Load the application's CMDB metadata checker by file path |
| stdlib | `json` | Manifest and other structured installation records |
| stdlib | `os` | File permissions and atomic writes |
| stdlib | `pathlib` | Paths and source/target ownership checks |
| stdlib | `shutil` | Copying and filesystem management |
| stdlib | `tempfile` | Atomic replacement of managed installation files |

For an explicitly required role-aware client/server installer, **approved optional stdlib modules** are `grp`, `ipaddress`, `re`, `secrets`, `subprocess`, `sys`, `time`, `tomllib`, `urllib.error` and `urllib.request`, as demonstrated in DevLog's pinned `deploy.py`. Import only those needed for the chosen role and lifecycle. No Flask, Click/Typer, Fabric, Ansible, new deployment daemon or third-party installer framework may be introduced without user approval and a specification revision. Installed application packages and their dependencies follow the selected application component contracts, not the installer module allowlist.

## Mandatory installation footprint

**Every successful installation owns a directory at the application constant `D<Name>.BASE_DIR`, normally `/opt/prod/<lowercase-app-name>`.** This includes client-only machines and installations where the useful payload is only a Python module or an executable.

- Record the **last successfully installed version** as plain text at `<BASE_DIR>/.deployment-version`, matching the literal `D<Name>.VERSION` (and the package's declared version, when applicable). Never advance the marker before install/upgrade verification succeeds.
- Keep a readable copy of `<app>/constants/D<Name>.py` in the installation, so CMDB can inventory the name, version and declarations without importing application modules or depending on a running service.
- Record ownership with the existing `<BASE_DIR>/.installation-manifest.json`. The installer must distinguish its managed files from configuration, credentials and user data. A minimal custom library or CLI may install only its metadata, executable/package artifact and any necessary configuration.
- If an installation has **multiple roles**, record the installed role in `<BASE_DIR>/conf/installation.json` (e.g. `{"role":"client"}` or `{"role":"server"}`). Keep that record after upgrade; do not infer role from the host or re-select the opposite role. A single-role project needs no artificial role switch.
- The application-owned installation's marker is authoritative for what was *successfully installed*, not what is currently checked out in Git, nor what was merely built. Uninstall removes active managed files and the successful-version marker; it preserves persistent/user data and a safe ownership tombstone when retained data prevents removing the directory.

For the smallest library-only project, use the existing installer with a focused source list, **not a second installer framework**. The `COPY_TREES` and `COPY_FILES` configuration can install just the canonical constants/marker plus a package artifact if the application's actual packaging places executable code elsewhere. Validate that the named artifact is installed and usable before writing the success marker. Avoid pretending the metadata marker itself installed an absent package.

## Entry points and installation roles

Three executable entry points are **always mandatory** in the application repository:

| Entry point | Required behaviour |
| --- | --- |
| `scripts/install.sh` | Perform first installation using the explicitly selected topology and prerequisites |
| `scripts/upgrade.sh` | Upgrade an existing installation; retain role, configuration, credentials, persistent data and user-facing commands |
| `scripts/uninstall.sh` | Remove only owned deployed code, links, units and schedules; keep data/configuration unless the user explicitly authorized purging it |

An application supporting both a client and a server on **different machines** may also provide `scripts/install-server.sh` as a fourth entry point. In that topology, follow DevLog's established names: `install.sh -server HOST` installs **only the client**, while `install-server.sh` installs the server plus any local client functionality the app explicitly requires.

- **Operation-specific dependency preflight:** before any host changes, check each external executable actually required by that operation and installed role. `--check` must use the **same prerequisite checks** without making host changes. For example, fresh server provisioning that calls `mariadb` must fail preflight when that executable is absent; client installs and non-provisioning server upgrades must not require a database administrator executable. Test both false success and false refusal paths.
- **Client install:** install only the client's declared executables, Python dependencies, endpoint configuration and version marker. Its **installed CMDB metadata must describe the client role**, not advertise server databases or local listeners absent from the client. If source constants describe the full server, generate a client-specific *installed metadata copy* while keeping the original source and canonical version/codename unchanged. It **must not** provision MariaDB, create systemd services/accounts, write server-only credentials or install server-only dependencies. Validate its `-server` host before making changes; it need not be reachable at installation time.
- **Server install:** install the server's declared services and local client only where required. Validate database permissions, service files and readiness and register owned resources for eventual uninstall. Do not copy credentials into the client package.
- **Upgrade:** inspect the existing installation identity and preserve its role. A client stays a client and a server stays a server, with no opportunistic conversion. Preserve endpoint settings, secrets and data. If a new release cannot start, retain the last-successful version marker and implement the app's required rollback or explicit recovery.
- **Uninstall:** mirror both role-specific installations. Remove only what that role owns and avoid changing unrelated services or database contents. The absence of a tested uninstall operation is an incomplete lifecycle, even when install and upgrade already work.

Server-only and library-only applications continue using ordinary `install.sh`, without needing a meaningless `install-server.sh`.

## Application-build workflow

1. **At bootstrap**, install the canonical release/lifecycle templates and this pinned skill. Keep `DEPLOYMENT_READY = False`; never execute an installer, create `/opt/prod` directories or modify the host while merely preparing a repository.
2. **When application requirements are known**, decide installation topology: single-role, library/CLI-only or client/server. Use the original `scripts/install.py` for simple file deployments. Where explicitly needed, adapt DevLog's role-aware Python `deploy.py` pattern and tiny shell wrappers, not its product-specific commands or credentials.
3. Configure the application-owned payload, `BASE_DIR`, role marker if applicable, dependency groups and the preserved state paths. Only then enable readiness and implement **all three** lifecycle operations and any selected `install-server.sh`.
4. Add tests for each role and each operation in disposable directories. Simulate failure after staging and before readiness, and check the marker/version and rollback boundary. For any real systemd/database changes, test in an explicitly disposable environment.
5. Before the **first release**, verify that deployment is truly enabled, source files are committed, all mandatory entry points are executable, `--help` works without privilege, and normal install/upgrade/uninstall plus `--check` semantics are tested. `new-release.sh` only checks some preflight mechanics: its success does **not** prove the installer was implemented.
6. Apply the literal `BMFORGE_COMPONENT = {"id": "bmforge.installation", "spec_version": "0.1.1"}` marker in the owning installation Python module. A marker alone does not certify readiness.

## Frozen reference examples

- **BMForge's own source-file installer**, `templates/project/scripts/install.py`, thin `install.sh`, `upgrade.sh`, `uninstall.sh` wrappers and tests in `tests/test_installation.py`: reusable managed-file ownership, safe uninstall and the successful-version marker. Use this as the normal starting point.
- **DevLog** `NadimGhaznavi/devlog` at commit `e236654caff205700b2d84531d32df51ca42cb8f`, locally frozen under `components/reference/devlog/`: `scripts/deploy.py`, `install.sh`, `install-server.sh`, `upgrade.sh`, `tests/test_deployment.py` and `docs/architecture.md`. These illustrate client/server role separation, a persisted role, release directories and a `current` pointer.

**The pinned DevLog revision does not contain `scripts/uninstall.sh`, and its role-specific installer does not implement that operation.** Treat this as an identified **gap** to prevent in new projects, not as a complete install/upgrade/uninstall template. Do not modify DevLog or copy its product-specific database provisioning into other applications.

## Acceptance checks

1. The fresh repo contains the three executable entry-point scripts plus the configured reusable helper. Bootstrapping itself changes **no installed machine state**.
2. A minimal library-only installation creates `BASE_DIR`, a readable app identity, an ownership manifest and `.deployment-version` without creating a database or service.
3. Installing twice is safe according to the application's declared policy; an upgrade preserves user data, config, credentials and the installed role.
4. Client-only `install.sh -server HOST` refuses missing/invalid hosts before side effects, installs no server-only resources, remembers the endpoint, and does not advertise local server resources in installed CMDB metadata. Fresh server install or `--check` must **not report success** when its required `mariadb` provisioner is absent; non-provisioning upgrades and clients must still pass without it.
5. Where selected, `install-server.sh` installs the service and any local client deliberately; separate client and server dependencies and tests remain separate.
6. Upgrades retain client/server roles and record the new version only after verification. Failures do not falsely report success; an application with rolling activation verifies its rollback or recovery contract.
7. Uninstall removes managed files, units and launchers for each supported role while retaining data and configuration, including repeat-uninstall and reinstall cases.
8. Installation metadata and `pyproject.toml` package version (when present) match the literal `D<Name>.VERSION`. The standard `new-release.sh` updates both together and rejects drift before merging. Successful installation markers never claim an uninstalled or failed version.
9. No alternate installer framework, direct app-to-app imports or new dependencies were introduced without explicit approval. Tested installation and release processes remain separate.

---

[Installation Scripts]({{ site.baseurl }}{% link pages/installation-scripts.md %}) · [Codex Skills]({{ site.baseurl }}{% link pages/codex-skills.md %}) · [Back to BMForge]({{ site.baseurl }}{% link index.md %})
