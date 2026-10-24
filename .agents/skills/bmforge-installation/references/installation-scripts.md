---
title: Installation Scripts
lang: en
locale: en-US
language_name: English
translation_key: bmforge-installation-scripts
---

Every project provides executable `scripts/install.sh`, `scripts/upgrade.sh`, and `scripts/uninstall.sh`. The Codex greenfield bootstrap already copies the existing templates plus `scripts/install.py` and `scripts/new-release.sh`; deployment is deliberately disabled (`DEPLOYMENT_READY = False`) until the app's installation contract is implemented. For manual projects, establish these entry points during setup.

## Define the Lifecycle

| Script | Responsibility |
| --- | --- |
| `install.sh` | Validate prerequisites, provision required resources, deploy the application, configure owned services and schedules, and verify the result |
| `upgrade.sh` | Update an existing installation while retaining configuration, credentials, and persistent data; apply required migrations and restart affected services |
| `uninstall.sh` | Stop and remove owned services and schedules and remove managed application files while retaining configuration, credentials, databases, and persistent data |

All three scripts support `--help` without privileges or changes. Validate arguments and prerequisites before modifying the host. Operations under `/opt/prod` require root. Run from a separate source checkout, regardless of the caller's working directory. Scripts report failures with a nonzero exit status and support a read-only `--check` where useful.

Keep shared deployment mechanics in one helper instead of duplicating them across the entry points. Reuse provisioning only when it is safe during upgrades. Document prerequisites, retained state, and any project-specific behavior in the project's installation guide.

## Mandatory installed identity and minimal library installs

**Every successfully installed BMForge-derived project owns `D<Name>.BASE_DIR`**, normally `/opt/prod/<lowercase-name>`. This applies even when there is no server, no local database and no executable beyond a custom Python library or CLI. A successful installation must leave:

- A plain-text `.deployment-version` holding the **last successfully installed** literal `D<Name>.VERSION`. If the project has a `pyproject.toml` version, validate that it agrees.
- The installed `<slug>/constants/D<Name>.py` readable by CMDB, so inventory does not require importing a package or contacting a running service.
- The existing `.installation-manifest.json` identifying the installed project's managed files. An application can keep its actual package in an isolated environment or elsewhere when explicitly required, but it must truly install/verify the declared payload before writing its success marker.

The current BMForge `templates/project/scripts/install.py` already implements this footprint. For a **minimal library-only install**, set `COPY_TREES = ()` and `COPY_FILES` to the canonical constants plus the actual package artifact as appropriate; implement the installation/verification step if it uses `pip` or another application-selected mechanism. Do not build a second file installer just to create a version marker. `DEPLOYMENT_READY = False` protects the bootstrap until Codex has implemented the real requirements.

## Select an installation topology

When implementing the application, choose the topology from its actual requirements:

| Topology | Required entry points | Expected installed footprint |
| --- | --- | --- |
| Library/CLI only | `install.sh`, `upgrade.sh`, `uninstall.sh` | Version and ownership metadata, installed library/CLI, no fabricated service |
| Single-machine server | The same three | Version metadata, application, selected services/DB integrations |
| Client + server on different machines | The three plus optional `install-server.sh` | Client-only install records the client role/endpoint; server install owns server dependencies, services and any required local CLI |

For a split client/server application, DevLog provides a [frozen source reference]({{ site.baseurl }}{% link pages/component-installation.md %}): `scripts/install.sh -server HOST` installs **only** the client; `scripts/install-server.sh` installs the server; and `upgrade.sh` reads `conf/installation.json` to preserve the role. Do not infer a server role from the presence of an HTTP or ZeroMQ component.

- Client-only installation must validate `HOST` before changes and must not create systemd units/accounts, provision MariaDB, or install server-only packages. The remote server need not be online at installation time.
- Server installation may require additional provisioning/health verification, but only when demanded by application requirements. Keep secrets out of client-only installations.
- An upgrade preserves the **installed role**, endpoint configuration, credentials and data. A failed activation does not advance the successful-version marker or report success.
- Uninstall must exist for each selected installation role and remove only owned deployed files and service resources while preserving persistent/user data. **DevLog's pinned source has no `uninstall.sh`**, so it is a partial reference, not the complete desired lifecycle.

These role-aware additions belong in the consuming application's own deployment helper, not an invented generic platform. They must follow the fixed [Installation Lifecycle contract]({{ site.baseurl }}{% link pages/component-installation.md %}) and reuse the existing release scripts.

## Build-time completion gate

Bootstrapping a repository **prepares but cannot complete** the install/upgrade/uninstall behaviour of an application not yet implemented. Before its first release, Codex must finish that work, enable deployment only when truly ready, and demonstrate successful first install, role-specific upgrade, uninstall, repeat uninstall, retained-data behaviour and the installed version marker in disposable environments. A readable `--help`, executable scripts and a successful Git release preflight alone are **not** proof that deployment is complete.

## Start from the Templates

Copy the [install]({{ '/templates/project/scripts/install.sh' | relative_url }}), [upgrade]({{ '/templates/project/scripts/upgrade.sh' | relative_url }}), and [uninstall]({{ '/templates/project/scripts/uninstall.sh' | relative_url }}) entry points and their [Python helper]({{ '/templates/project/scripts/install.py' | relative_url }}) into the project's `scripts/` directory. Include the metadata checker from [CMDB Compliance]({{ site.baseurl }}{% link pages/cmdb-compliance.md %}).

```sh
chmod +x scripts/install.sh scripts/upgrade.sh scripts/uninstall.sh
```

The helper is a source-file deployment baseline. Replace its project name and package placeholders, define its managed file and directory lists, and implement any provisioning, service lifecycle, schema migration, and health checks the project needs. It starts with `DEPLOYMENT_READY = False` and refuses deployment until that work is ready. Stubbed steps must not report success.

For a source-only toolkit, the baseline can be sufficient once its file lists are configured. [BMForge's installation]({{ site.baseurl }}{% link pages/installing-bmforge.md %}) is an example. Applications with running services or databases need their own additional work before enabling deployment.

## Configure Applications Before Service Changes

Implement [Runtime Configuration]({{ site.baseurl }}{% link pages/runtime-configuration.md %}) for deployment settings in `conf/<lowercase-name>.json`, including defaults from constants, shared validation and resolution, CMDB read access, and preservation through the application lifecycle.

For applications with listeners, implement [Network Configuration]({{ site.baseurl }}{% link pages/network-configuration.md %}) as part of the lifecycle work. Create production JSON from `CMDB_NETWORK` only when missing and preserve existing files during reinstall and upgrade. Validate configuration before stopping services, share resolved settings with health checks, and provide a restart entry point that applies all affected settings. The starter helper does not implement these application-specific steps.

## Preserve Data and Deployment Identity

Deploy to the literal `BASE_DIR` and install readable constants at the path specified by [CMDB Compliance]({{ site.baseurl }}{% link pages/cmdb-compliance.md %}). Directory permissions must allow the inventory account to traverse the path and read the metadata. Credentials stay outside public source files.

Use explicit managed file lists or an ownership manifest. Keep persistent data and live configuration outside copied source trees. The baseline does not infer protected data paths from CMDB declarations; configure and test that separation explicitly. Refuse unexpected paths and symlinks, preserve unowned files, and remove only project-owned resources. Uninstallation is not a data purge.

The baseline records ownership in `.installation-manifest.json` and the last successful version in `.deployment-version`. When uninstallation retains unowned files, it leaves an empty ownership record so subsequent installation or removal can recognize the directory. Constants are copied after other managed files; the successful-version marker advances only when the operation completes. Individual files are replaced atomically, but the whole deployment is not transactional. An interrupted operation can leave mixed application files; report the failure and inspect or retry from the source checkout.

## Connect Releases and Verify

Release publication and host deployment are separate processes. Run installation or upgrades from the intended release checkout. The release script checks that the three lifecycle entry points are executable, have valid shell syntax, and are committed; it does not run them or certify their project-specific behavior.

For installed running services, use their existing [application health check]({{ site.baseurl }}{% link pages/health-checks.md %}) when verifying startup or restart. A healthy process or listening port alone does not certify required application dependencies. Do not add a second probe service.

For selective upgrades, include lifecycle scripts and their dependencies in [Deployment Impact Tracking]({{ site.baseurl }}{% link pages/deployment-impact-tracking.md %}). Preserve the last successful version before replacing application files, execute the planned work, and publish success bookkeeping after health checks.

Verify first installation, reinstallation, upgrades, repeat uninstallation, retained configuration and data, removed obsolete files, readable CMDB metadata, invalid paths, and interrupted work. Run filesystem checks in temporary directories and service or database checks in an appropriate disposable environment. Verify a real CMDB scan after deployment, including runtime configuration, declared component paths, and same-host database connections. Test declared backups and effective listener bindings separately; discovery does not check directory existence or application health.

---

[Back]({{ site.baseurl }}{% link index.md %})
