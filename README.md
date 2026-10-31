# DevLog

Personal time tracking for work in GitHub repositories. One persistent systemd
service stores tasks and active intervals in MariaDB and serves a daily-hours
report. Repository commands operate on the repository containing the current directory.

```bash
dl status                      # show the globally running task from any directory
dl start                       # start or resume this repository's task
dl pause                       # pause it
dl start                       # resume it
dl commit "Implement lookup"   # git add . -v; commit; record task/SHA; push
dl publish                     # invoke the repository's existing release script
dl releases sync               # catch up existing release tags, or recover recording
```

`dl status` queries the server without changing the timer. It prints
`No task currently running` or
`Repository (bmforge): Task #17 running for 02:35 hours`, using the active
repository's short name, task ID and total active time in `HH:MM` (excluding
pauses). Hours can exceed 24. Paused tasks are not running.

`dl pause` prints `Repository (mycount): Task #12 paused on 2026-10-25 11:30:00`,
using the saved pause time in the configured timezone. Messages for an already
paused task or no task remain unchanged.

Starting in another repository pauses the previous task automatically. Only one
task accrues time at once. A successful commit completes its task even when the
subsequent push fails. Resolve Git conflicts yourself; DevLog never pulls,
rebases, force-pushes, or retries a push automatically. Run `dl start` to begin
the next task after a commit. Both active and paused tasks can be committed.

`dl publish` runs the first existing script among `new_release.sh`,
`scripts/new_release.sh`, and `scripts/new-release.sh`, from the repository root.
Pass script arguments after `--`, for example `dl publish -- --help`. The timer
is unchanged. The release script remains responsible for its release workflow.
After a successful script, DevLog records version tags that appeared during the
call. Release rows appear alongside tasks in project and daily reports, with a
dark amber background and labels such as `Release v0.15.4 (neptune)`. They never add
tracked time. Reports read release data from MariaDB; the server never runs Git.

For the one-time catch-up, run these commands in each project's checkout after
upgrading the DevLog server and client:

```bash
dl releases sync --dry-run      # inspect JSON metadata; no service call or writes
dl releases sync               # record all local version tags
```

Sync reads local `vX.Y.Z` or `X.Y.Z` tags, including prerelease/build suffixes,
that resolve to commits. It never fetches; obtain any missing tags separately
before syncing. Annotated tags use their tagger timestamp. Their standard
`Release X.Y.Z: codename` annotation supplies the optional codename. Lightweight
tags use the commit's committer timestamp because Git does not retain their
creation time; unrecognized annotations and lightweight tags omit the codename.
Release timestamps are stored in UTC and displayed in the report timezone.

Repeating sync is safe, including after a partial catch-up or uncertain reply.
An existing repository/tag with different metadata is rejected for inspection.
If publishing succeeds but recording fails, DevLog reports failure and prints
`dl releases sync` as the recovery command. Run sync rather than publishing the
same release again. Sync does not require a running task or change its timer.
Schema initialization creates the additive releases table; the existing server
upgrade process runs this initialization before activating the new version.

## Publishing a release

DevLog owns its release files independently of BMForge. The project-specific
`scripts/new-release.sh` is generated from the BMForge release template and
retains the familiar feature → dev → main, annotated tag and atomic-push workflow.

```bash
scripts/new-release.sh 0.1.1 "Maintenance"
```

The release script validates that `DDevLog.VERSION` and the static
`pyproject.toml` `[project].version` agree **before** modifying Git branches.
It updates both versions and the DevLog changelog in the release commit. It
never installs or upgrades the application itself. Resolve your branch history
and ensure the release metadata and installer entry points are committed before
releasing.

## Install a release

Cut your Git release, then run these scripts from the prepared release checkout;
they do not pull or change Git. Both installation types require Python **3.11+**
with venv/pip support and Git. Every server installation, including a reinstall
with saved credentials, additionally needs the `mariadb` command to provision
the database and account. `install-server.sh --check`
verifies this before any account, filesystem or database changes. Client-only
installs and server upgrades do not require the MariaDB administrator command.

### Client only

On your development machine:

```bash
sudo ./scripts/install.sh -server 192.168.1.20
# Or use a hostname:
sudo ./scripts/install.sh -server devlog.example.net
```

`-server <IP or hostname>` is mandatory. The client connects to that server on
ZMQ port **19701**. Its address is saved as `client.host` in
`/opt/prod/devlog/conf/devlog.json`; edit that file to change the address later.
Client installation provides **`/opt/prod/devlog/bin/dl`** and its Python
environment. It does not require or configure MariaDB, systemd, a service account,
or server-only Python dependencies. The server need not be online during installation.

### Server

On the server machine, additionally provide Linux/systemd, a running local
MariaDB installation, and socket administrator access through
`sudo mariadb --protocol=socket --skip-ssl --user=root`:

```bash
sudo ./scripts/install-server.sh
```

Server installation includes the local CLI, creates the `devlog` system account, a local `devlog` database/user,
and a random database password in `/opt/prod/devlog/conf/database.env` (root-owned,
mode 640, readable by the service group). Credentials are never shell-sourced or
passed as command-line arguments. If that file already exists, installation reuses
its credentials and recreates any missing database/account resources, restoring
the account's password and grants. New credentials are generated only when the
file is absent. The installer manages the local `devlog` database and
`devlog`@`localhost` database account; an optional `DB_SOCKET` selects the local
MariaDB instance. Database tables are initialized explicitly
by the installer; the running server never creates schema.

### Installation identity and dry-run checks

All client and server installations create `/opt/prod/devlog/`, including
`devlog/constants/DDevLog.py` for CMDB discovery,
`.installation-manifest.json` for installed file/release ownership, and
`.deployment-version` for the **last successfully activated** version.
On a client-only machine, the installed CMDB copy suppresses server-only
database and listener declarations. The source application's constants and
server installation retain the canonical declarations. These are installation
records, not a separate server or runtime framework.

Before installing, upgrading or uninstalling, use `--check` without privileges
to validate known prerequisites without changing the host:

```bash
./scripts/install.sh -server devlog.example.net --check
./scripts/install-server.sh --check
./scripts/upgrade.sh --check
./scripts/uninstall.sh --check
```

### Upgrades

On either machine, after preparing a later release:

```bash
sudo ./scripts/upgrade.sh
```

The installer records whether the machine is a client or server in
`/opt/prod/devlog/conf/installation.json`. Upgrades retain that role: client
upgrades preserve the configured server address and do not touch database or
systemd resources. Server upgrades preserve credentials and timing records and
do not require database administrator access. Original server installations from
before this split are recognized by their server command and database credentials.

### Uninstall

From the release checkout, run:

```bash
sudo ./scripts/uninstall.sh
```

Uninstall removes the entire DevLog installation, including all release
directories, configuration, installed CMDB constants and installation/version
records. On a server it also stops and removes the systemd service, drops the
DevLog database and database account, and removes the `devlog` system account
and group. Server uninstall requires the `mariadb` command and local root socket
access, as server installation does. Its `--check` checks prerequisites without
changing files or connecting to MariaDB.

**The sole retained file is `conf/database.env`**, when present. Uninstall leaves
it owned by root with mode 600. A client without credentials leaves no installation
directory. Client uninstall affects its local installation; server resources are
removed by uninstalling on the server.

Reinstalling the server reuses those saved credentials, creates an empty database,
and restores the service account's access to the credential file. All other
configuration starts from the shipped defaults. Upgrades continue preserving
configuration, credentials and logged data. Repeating uninstall is safe, and the
new uninstaller also removes data retained by an older uninstall that left its
ownership manifest. Legacy installations without a manifest must first be
upgraded to adopt that record before uninstalling.

Each installation builds an isolated release environment under
`/opt/prod/devlog/releases/`. `current` selects the installed release, and the
command is **`/opt/prod/devlog/bin/dl`**. Server upgrades prepare the new environment
before stopping the service and restore the previous executable release if startup
validation fails. Old releases are retained.

```bash
export PATH="/opt/prod/devlog/bin:$PATH"
# On the server machine:
systemctl status devlog.service
journalctl -u devlog.service
```

The report is at **http://<server>:19700/**; ZMQ listens on **19701**. Both bind
to `0.0.0.0`. Configuration lives in `/opt/prod/devlog/conf/devlog.json`; initial
defaults are in `conf/devlog.json`. Edit the file and restart the service to
change interfaces, ports, client host, timeouts, or report timezone (initially
`America/Toronto`). Keep these unauthenticated listeners on your trusted network.

### Correcting completed task timing

**Projects**, after **Tasks** in the main navigation, shows all recorded tasks
and releases for one project, with full active durations and total time across
all dates. Its dropdown selects the first project by default and switches
projects immediately; there is no `*` option. Dates appear beside start times.

**Daily** lists today's tasks across all projects, with a date picker for other
days and a Project column after Task #. Between the date and **Show Report**, a
Project dropdown lists `*` for all projects plus projects with recorded work on
that day. Selecting a project filters the task rows and total time; changing to
a day without work for that project resets the selection to `*`.
Click the total above a chart bar to open
that day's Daily Task Report across all projects, or click a colored chart
segment to see that day's tasks for that repository. Hover labels and daily
totals show hours and minutes (`HH:MM`), rounded to the nearest minute. The main
Daily Tasks chart is 680 px tall; its former Tasks section is removed.
**Tasks** opens the whole filtered period and includes the selected project in
its title. Open a task to inspect its commit, active intervals and pauses.
Task-list hours cover the selected period; task details show the whole task.
**Back to report** shows all repositories for the selected period.

Completed tasks use vis-timeline 8.5.6 to edit their existing work ranges.
Choose a task-step from the dropdown to show just that step, then drag its block
or resize either edge. Each completed
pointer gesture saves through the server; the range is accepted only after the
server confirms it. The completion marker is locked.
Work cannot extend beyond completion or overlap another task, including work
outside the selected view. Commit and lifecycle timestamps stay intact.

The timeline automatically fits the selected task-step, including after saved
corrections. Panning and zooming are disabled. Above it, a two-column table holds
the step dropdown, Start, End and the step's live elapsed time. The axis and
precise editing fields use **browser-local time**. Start and End display
`YYYY-MM-DD HH:MM:SS`, with calendar controls alongside. To edit with a keyboard,
enter the local start and end, then **Save timing**.
**Cancel** discards the unsaved form values. Double-clicking a work range opens
that same form. Task hours update from the accepted server snapshot. Unchanged
fields preserve their saved fractional seconds. Nonexistent local times are
rejected; an edited time repeated when clocks go back requires an explicit offset
suffix such as `-04:00` or `-05:00`.

Stale edits and uncertain saves refresh the recorded timing before further edits;
failed refreshes leave editing disabled with a reload link. Writes are never
retried automatically. The read-only recorded intervals remain available without
JavaScript or if the pinned unpkg.com timeline assets cannot load.

The interactive task detail page uses browser-local time for its metadata,
last-updated timestamp and selected recorded interval as well as the editor.
The read-only fallback and task lists display timestamps as `yyyy-mm-dd hh:mm:ss`
in the configured report timezone. Each interval also shows elapsed time as `HH:MM:SS`, with
hours continuing beyond 24 for longer intervals.

Saving recalculates daily/project totals and rejects crossed boundaries,
overlaps with other tasks, and stale edits. The task's original lifecycle
timestamps and Git commit remain intact; corrected work remains discoverable
in date-filtered task lists. This editor adjusts existing work blocks on
completed tasks. Unfinished tasks retain the closed-interval pause form; open
intervals must be paused with `dl pause` before using that form.

The service does not access Git checkouts. The CLI derives repository identity
from its GitHub `origin`, supporting HTTPS and SSH remotes; checkout paths are
never sent. To connect to another service host:

```bash
dl --server tcp://server-name:19701 start
# Or set DEVLOG_ENDPOINT, or client.host in devlog.json.
```

## Failures and recovery

A Git staging/commit failure leaves the task unfinished. If the service is
unavailable before committing, Git is untouched. If the local commit succeeds
but recording completion cannot be confirmed, the CLI prints its SHA and recovery
command:

```bash
dl commit --record FULL_COMMIT_SHA
```

This records an existing commit on the current branch without creating or pushing
another commit. Repeating it for a SHA already recorded is harmless. Push a
previously unpushed commit with ordinary `git push` after resolving the cause.
Open timers continue across service restarts; use `dl pause` when leaving work.

## Development and verification

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[server]' pytest
DEVLOG_DATABASE_ENV=/path/to/test-database.env .venv/bin/dl-db-init --config conf/devlog.json
DEVLOG_DATABASE_ENV=/path/to/test-database.env .venv/bin/dl-server --config conf/devlog.json
.venv/bin/python -m pytest
```

Ordinary tests use disposable Git repositories and ephemeral loopback listeners.
Database integration tests run only when `DEVLOG_TEST_DB_SOCKET` points to an
explicitly disposable MariaDB instance. They create/drop their own uniquely named
database; optional `DEVLOG_TEST_DB_USER`/`DEVLOG_TEST_DB_PASSWORD` configure the
test administrator. Never point these variables at production.

An optional browser acceptance check uses Playwright/Chromium as test-only tools:
set `DEVLOG_TEST_BROWSER=1` along with the disposable database socket. It verifies
the pinned assets, charts, repository selection, vis-timeline gestures, precise
editing, failed-save recovery and mobile layout. For offline runs,
`DEVLOG_TEST_PLOTLY_ASSET` may point to the approved Plotly 4.1.1 asset;
`DEVLOG_TEST_TIMELINE_JS` and `DEVLOG_TEST_TIMELINE_CSS` may point to the approved
vis-timeline 8.5.6 files. These only intercept requests in tests.

See the [changelog](CHANGELOG.md) for version history. Before cutting a release,
date its changelog entry and record any additional user-visible changes.

See [architecture](docs/architecture.md), [wire protocol](docs/protocol.md), and
the pinned [BMForge lock](.agents/bmforge/lock.json) for implementation contracts.
