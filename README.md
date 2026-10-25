# DevLog

Personal time tracking for work in GitHub repositories. One persistent systemd
service stores tasks and active intervals in MariaDB and serves a daily-hours
report. The CLI operates on the repository containing the current directory.

```bash
dl start                       # start or resume this repository's task
dl pause                       # pause it
dl start                       # resume it
dl commit "Implement lookup"   # git add . -v; commit; record task/SHA; push
dl publish                     # invoke the repository's existing release script
```

Starting in another repository pauses the previous task automatically. Only one
task accrues time at once. A successful commit completes its task even when the
subsequent push fails. Resolve Git conflicts yourself; DevLog never pulls,
rebases, force-pushes, or retries a push automatically. Run `dl start` to begin
the next task after a commit. Both active and paused tasks can be committed.

`dl publish` runs the first existing script among `new_release.sh`,
`scripts/new_release.sh`, and `scripts/new-release.sh`, from the repository root.
Pass script arguments after `--`, for example `dl publish -- --help`. The timer
is unchanged. The release script remains responsible for its release workflow.

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
with venv/pip support and Git. Fresh server provisioning additionally needs the
`mariadb` command when new DB credentials must be created. `install-server.sh --check`
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
passed as command-line arguments. If that file already exists, installation uses
it instead of provisioning credentials. Database tables are initialized explicitly
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

Uninstall removes DevLog-owned launchers, managed release directories, the
installed CMDB constants, version marker and, for server installations, the
DevLog systemd unit. It retains `conf/devlog.json`, database credentials,
MariaDB data and other unowned files. The installation manifest remains as an
empty ownership record when configuration is retained. Repeating uninstall is
safe. Legacy installations without a manifest must first be upgraded to adopt
the ownership record before they can be uninstalled safely.

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

### Correcting a forgotten pause

Click a date in the report table to see its tasks, or click a colored chart
segment to see that day's tasks for that repository. **Tasks** opens the whole
filtered period. Open a task to inspect its commit, active intervals and pauses.
Task-list hours cover the selected period; task details show the whole task.

Under the affected active interval, choose **Insert a pause**, enter **Pause
began** and **Work resumed**, and save. For example, an overnight break might run
from `2026-10-24T22:00` to `2026-10-25T08:00`. Leave **Work resumed** blank to
exclude time through that interval's recorded end. Times without an offset use
the configured report timezone; an explicit offset such as `-04:00` resolves
ambiguous daylight-saving times.

Saving subtracts the break from active time and recalculates the daily/project
totals. The task's original start, completion time and Git commit remain intact.
Only closed active intervals can be corrected; run `dl pause` first if the
affected interval is still running. A pause must fit within one active interval.
Corrections commit atomically, and stale forms must be reloaded before editing.

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
the pinned Plotly asset, chart values, repository selection, pause editing and
mobile layout. For offline runs, `DEVLOG_TEST_PLOTLY_ASSET` may point to a cached
copy of the approved Plotly 4.1.1 asset; this only intercepts requests in tests.

See the [changelog](CHANGELOG.md) for version history. Before cutting a release,
date its changelog entry and record any additional user-visible changes.

See [architecture](docs/architecture.md), [wire protocol](docs/protocol.md), and
the pinned [BMForge lock](.agents/bmforge/lock.json) for implementation contracts.
