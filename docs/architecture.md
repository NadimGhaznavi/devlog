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

`LocalRepository.release_tags` reads local version tags and resolves their
commits. Annotated tags supply the tagger timestamp and, for the standard
`Release X.Y.Z: codename` annotation, the codename. Lightweight tags use the
commit's committer timestamp and have no codename. There is no automatic fetch.
`dl releases sync` passes each release through `activity/ReleaseSync` to the
existing ZMQ worker; `--dry-run` prints JSON without contacting the service.
`dl publish` snapshots existing tags and sends newly available version tags only
after its script returns success. Recording failure preserves the published
release and identifies sync as the recovery operation. Neither operation
changes task tracking state.

Domain SQL and atomic transitions belong to `interface/TaskDb.py`. A singleton
database row serializes mutations. Unique generated columns enforce one open
interval globally and one unfinished task per repository. Database transactions
roll back all changes if switching repositories fails. Every worker owns its
database connection; there is no shared connection or ORM.

The additive `releases` table references `repositories` and stores the exact
tag name, optional codename, commit SHA, UTC release timestamp and server
recording timestamp. Its unique repository/tag key makes exact retries harmless;
changed metadata is a conflict. A repository-row lock serializes concurrent
recordings. Release writes use their own transaction and never lock or mutate
the tracker singleton. Explicit `dl-db-init`, already called by server upgrades,
creates the table idempotently; request handling never changes the schema.

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
exact approved CDN URL. If the chart cannot load, a link opens the Daily Task
Report for the selected end date. No frontend build, Python plotting package,
maps, or graph library is introduced.

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

The 680 px Daily Tasks chart displays hover durations and totals above each bar
as `HH:MM`, rounded to the nearest minute. Each total is a keyboard-accessible
link to `/daily` for its date, with repository and range filters removed. Totals
continue to reflect visible projects when the legend changes. The main page's
separate Tasks section and daily-hours table have been removed.

Daily total links open `/daily`, which lists one local day's tasks across all
repositories and defaults to today in the configured timezone. It reuses the
Tasks template, adds a Project column and offers date and project filters.
`TaskHistory.daily` derives the project choices from the unfiltered local day's
recorded hours and stored releases, then filters rows and total time by the
selection. The default `*` includes all projects; changing to a date without
work or releases for the selected project resets the selection to all projects.
Chart segments link to `/tasks`, filtered by day and repository. `/tasks/<id>` presents the
complete task timeline through `activity/TaskHistory`.

`TaskHistory.list` reads task and release summaries in one database snapshot,
merges them in descending UTC timestamp order, then formats local times. This
preserves ordering during repeated daylight-saving hours. Release rows use a
distinct dark amber style, no task link and no duration. Release-only projects remain
selectable on Daily pages. Releases contribute nothing to hours or chart bars.

The application-owned form endpoint `POST /tasks/<id>/pause` validates a bounded
same-origin form and passes its timestamps through the configured report timezone.
Ambiguous local DST times
require an explicit offset. These routes retain report filters and locale.

`TaskDb.insert_pause` holds the same singleton lock used by CLI transitions. It
replaces one closed active interval with up to two remaining active intervals in
one transaction. Pauses remain gaps between active intervals, so there is no
schema migration or change to report calculations. Replacement interval IDs
reject repeated/stale edits. Open intervals and task/commit metadata remain
unchanged; the task timeline also shows gaps at either end of a completed task.

Completed task pages use the pinned `bmforge.timeline` specification 0.1.0:
vis-timeline 8.5.6 standalone UMD JavaScript and matching CSS, loaded from their
versioned unpkg.com URLs. The app-owned adapter maps stable string interval IDs
to editable ranges and neighboring work/completion events to locked items.
vis-timeline owns selection, the axis, dragging and resizing. The adapter fits
the task and completion marker on load and snapshot refresh; pan/zoom is disabled. Its XSS
protection remains enabled, and application labels use DOM `textContent`.
`TaskHistory.read(include_editor=True)` supplies explicit-offset timestamps with
persisted precision, a revision digest, context and a server snapshot time.
The timeline and precise keyboard form deliberately use UTC; the recorded
interval list retains the configured report timezone. Durations mean elapsed time.

Completed drag/resize gestures and precise form saves share one persistence path.
The vis callback accepts canonical values only after server acknowledgement;
cancellation and failure settle it with null. The accepted snapshot refreshes
the ranges, context, total and recorded intervals. The precise form has explicit
Save/Cancel actions; create/delete and group movement are disabled. Uncertain
writes and stale edits trigger one authoritative read before further editing,
without retrying the write. Failed reads leave the editor blocked with a reload link.

`GET /tasks/<id>/timing` returns the authoritative task snapshot for recovery.
`POST /tasks/<id>/timing` accepts bounded, same-origin JSON and returns the accepted
task snapshot after persistence. `TaskHistory` validates
the payload and explicit timestamp offsets; `TaskDb.save_timing` holds the existing
singleton write lock, verifies the loaded revision and completed state, validates
interval order, the fixed completion bound and overlaps against all other tasks, then updates the existing
intervals in one transaction. Commit and lifecycle events remain unchanged; the
revision includes microseconds and all original interval IDs/timestamps. Task-list
date selection includes corrected intervals outside the original lifecycle span.
No schema change, frontend framework, build system or Python dependency is introduced.
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
