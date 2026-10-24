# Changelog

User-visible changes are recorded here, newest version first. Versions remain
marked **Unreleased** until a release is cut; replace that label with the release
date (`YYYY-MM-DD`) when publishing.

## [Unreleased]

### Fixed

- Reject escaped lone Unicode surrogates in incoming ZeroMQ JSON envelopes before activity dispatch. A malformed request receives `invalid_request` without terminating the socket worker; valid Unicode and subsequent requests still work.
- Make fresh server installation preflight (including `--check`) require the `mariadb` executable when database provisioning will use it. Client-only installs and non-provisioning upgrades do not acquire that dependency.


### Fixed

- Close the BMForge 0.9.0 installation lifecycle gaps: implement role-aware
  `uninstall.sh` and read-only `--check` support for install, install-server,
  upgrade and uninstall without changing the client/server dependency split.
- Publish an installation ownership manifest, readable CMDB constants, and
  a last-successful-version marker for both client and server deployments.
  Preserve configuration and database data during uninstall.
- Install a project-specific release script from the BMForge template, keeping
  `pyproject.toml` version synchronized with `DDevLog.VERSION` during releases.
- Validate source package and literal CMDB versions before host changes.

## 0.1.0 — Unreleased

### Added

- `dl start` and `dl pause` to start, pause, and resume repository tasks. Starting
  work in another repository automatically pauses the previous task, keeping one
  task active at a time.
- `dl commit <message>` to stage all repository changes, commit, record the task's
  commit SHA and message, and push. A failed push leaves the task completed.
- `dl commit --record <SHA>` to recover an unconfirmed task recording without
  creating or pushing another commit.
- `dl publish` to invoke a repository's existing release script without changing
  its timer.
- MariaDB storage for repositories, tasks, and active time intervals, with atomic
  task transitions and persistence across service restarts.
- A daily-hours report with repository and date filters, timezone-aware day
  boundaries, an interactive chart, and a table of recorded hours.
- One persistent systemd service with configurable HTTP and ZMQ listeners,
  defaulting to `0.0.0.0:19700` and `tcp://0.0.0.0:19701`.
- Application health checks through HTTP `/health` and the existing ZMQ interface.
- Installation and upgrade scripts targeting `/opt/prod/devlog`, including
  `/opt/prod/devlog/bin/dl`, isolated release environments, preserved configuration
  and credentials, and restoration of the previous executable release if an
  upgrade fails startup validation.
- English CLI and report message catalogues prepared for additional translations.
- Project-local, pinned BMForge skills and architecture documentation.

### Changed

- Split deployment into `scripts/install.sh -server <IP or hostname>` for the
  standalone `dl` client and `scripts/install-server.sh` for the database and
  systemd service. Client installation saves the required server address and
  installs only client dependencies.
- Upgrades preserve the installed client/server role and the client's server
  address; client upgrades do not manage database or systemd resources.
