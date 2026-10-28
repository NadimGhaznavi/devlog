# DevLog implementation

One systemd process runs the standard-library HTTP display server on
`0.0.0.0:19700` and a socket-owning ZMQ REQ/REP thread on
`tcp://0.0.0.0:19701`. MariaDB runs as its own existing database daemon.

```text
dl (local checkout) -- start/pause/commit metadata --> ZMQ worker
                                                     |
                                               activity/Tracking
                                                     |
                                                interface/TaskDb
                                                     |
                                                interface/DbMgr --> MariaDB
                                                     ^
HTTP report --> activity/Report ----------------------+
```

The CLI runs Git and release scripts on the local machine. `LocalRepository`
resolves the checkout and its GitHub identity. `CommitTask` checks that a task
exists before staging changes, coordinates the commit, and records completion
before pushing. `dl publish` invokes the repository's existing release script;
it is unrelated to the Git component's managed-file publication operation.
No release automation is invented or run by installation.

Domain SQL and atomic transitions belong to `interface/TaskDb.py`. A singleton
database row serializes mutations. Unique generated columns enforce one open
interval globally and one unfinished task per repository. Database transactions
roll back all changes if switching repositories fails. Every worker owns its
database connection; there is no shared connection or ORM.

`DbMgr.py` and `Localizer.py` are unchanged copies of their pinned canonical
templates. DevLog adapts the Git template with an `on_committed` callback between
the local commit and push to implement the user's explicitly agreed completion
boundary. The prescribed Git commands, module inventory, and managed-file
publication implementation are retained. No automatic pull or push retry is added.

Stable identifiers and configuration defaults live in domain-grouped constants.
English is the source message catalogue; the unchanged localizer supports future
supplied translations. Human UI labels and CLI application messages use stable
`DText` keys. Wire fields, statuses, Git output, and service logs stay untranslated.

The report uses Jinja2 autoescaping and browser-side Plotly.js **4.1.1** from the
exact approved CDN URL. An HTML daily-hours table remains available if that asset
cannot load. No frontend build, Python plotting package, maps, or graph library is
introduced.

Daily report rows include total hours and a `projects` mapping of repository
identities to hours. A `task_hours` mapping contains each project's positive task
durations for that day, ordered by task ID and combining resumed intervals.
The chart stacks these project hours into one bar per day, with consistent
project colors across filters and a legend below the Date label. Each project
segment has a darker 4 px border and 2 px horizontal task separators matching
the border color; the separators follow the visible stacks when projects are
hidden using the legend.
Horizontal separator strokes use crisp rendering and a darkened
version of the project color, shared with the bar border, for visibility.

Report dates link to `/daily`, which lists one local day's tasks across all
repositories and defaults to today in the configured timezone. It reuses the
Tasks template, adds a Project column and offers a date picker. Chart segments
link to `/tasks`, filtered by day and repository. `/tasks/<id>` presents the
complete task timeline through `activity/TaskHistory`. The application-owned form endpoint
`POST /tasks/<id>/pause` validates a bounded same-origin form and passes its
timestamps through the configured report timezone. Ambiguous local DST times
require an explicit offset. These routes retain report filters and locale.

`TaskDb.insert_pause` holds the same singleton lock used by CLI transitions. It
replaces one closed active interval with up to two remaining active intervals in
one transaction. Pauses remain gaps between active intervals, so there is no
schema migration or change to report calculations. Replacement interval IDs
reject repeated/stale edits. Open intervals and task/commit metadata remain
unchanged; the task timeline also shows gaps at either end of a completed task.

Completed task pages replace pause-entry forms with a DevLog-owned HTML/CSS and
ordinary JavaScript timing control. `TaskHistory.read(include_editor=True)`
supplies UTC timestamps with full persisted precision, string IDs, an interval
revision digest, fixed neighbouring work and a server page-load timestamp.
The browser draws proportional work blocks and gaps, handles pointer/touch and
keyboard boundary adjustments, and previews elapsed work without database writes.
Zoom changes only the visible time range. Other tasks and page-load time stay fixed.
The stored task completion time is a fixed marker and an upper bound for work.
This is the server's completion event, not a separately retrieved Git committer
timestamp; the editor never invokes Git or modifies commit metadata.

`POST /tasks/<id>/timing` accepts bounded, same-origin JSON. `TaskHistory` validates
the payload and explicit timestamp offsets; `TaskDb.save_timing` holds the existing
singleton write lock, verifies the loaded revision and completed state, validates
interval order, the fixed completion bound and overlaps against all other tasks, then updates the existing
intervals in one transaction. Commit and lifecycle events remain unchanged; the
revision includes microseconds and all original interval IDs/timestamps. Task-list
date selection includes corrected intervals outside the original lifecycle span.
No schema change, frontend framework or new runtime dependency is introduced.
The original pause endpoint remains available for unfinished-task forms and
existing clients. Completed interval records remain readable without JavaScript.

Pinned skill versions and source hashes are recorded in `.agents/bmforge/lock.json`.
There are no BMForge or reference-application imports at runtime.

Both client and server installs expose a standard BMForge installation identity
at `/opt/prod/devlog`: an installed `devlog/constants/DDevLog.py`,
`.installation-manifest.json` tracking owned resources, and
`.deployment-version` written only after successful activation. `--check`
preflights run without root or host changes. Role-aware
`scripts/uninstall.sh` removes the DevLog installation directory except for
`conf/database.env`. Server uninstall also drops the owned local database and
database account, removes the systemd unit and system account/group, and leaves
the credential file root-owned with mode 600. Reinstallation recreates the
database/account with those saved credentials and shipped configuration defaults;
upgrades preserve configuration and data. Server install and uninstall require
the MariaDB administrator client; upgrades and client operations do not.
Client-only installations
retain the canonical application version but suppress local server listener
and database declarations in the CMDB-readable installed constants. Server
installations retain the source declarations. All three lifecycle entry points
are completed, not inert bootstrap stubs.

Deployment is split between `scripts/install.sh -server HOST` for client-only
machines and `scripts/install-server.sh` for the server machine. Only the server
installer provisions MariaDB and systemd. The Python package's base dependency
is PyZMQ; the `server` extra adds Jinja2 and PyMySQL. Both installations provide
the public `bin/dl` path, and the server also provides `bin/dl-server` and
`bin/dl-db-init`. `conf/installation.json` records the role so `scripts/upgrade.sh`
can preserve it without upgrading a client into a server. DevLog's release script synchronizes the package's PEP 621 version with the canonical DDevLog constant. Installation rejects a mismatch before writing any files.
