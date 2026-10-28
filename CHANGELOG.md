# Changelog

User-visible changes are recorded here, newest version first. Versions remain
marked **Unreleased** until a release is cut; replace that label with the release
date (`YYYY-MM-DD`) when publishing.

## [Unreleased]

## [0.9.2] - 2026-10-28 @ 01:28

This release is named for the element **Promethium (Pm)**. Promethium has no 
stable isotopes, and even its longest-lived isotopes decay on human timescales.

### Summary

Match the Tasks page's repository title to its total-time display and align
their bottom edges for a consistent heading row. Tighten task table spacing
so more tasks fit on screen.

### Changed

- Use the total's orange color, font size and weight for the Tasks title,
  retaining left alignment and matching the smaller size on mobile screens.
- Bottom align the title with the total duration and let long titles wrap
  within the heading row.
- Reduce vertical padding in task table headers and cells, and shorten the
  task-number links' minimum height for more compact rows.

## [0.9.1] - 2026-10-27 @ 18:17

This release is named for the element **Neodymium (Nd)**. Neodymium is a key 
ingredient in extremely powerful permanent magnets found in motors and headphones.

### Summary

Bring the Tasks screen in line with the main report's visual style, with an
explicit repository heading, a prominent total-time summary and alternating
row backgrounds for easier reading.

### Changed

- Alternate task table row backgrounds using the existing dark palette to make
  descriptions and times easier to follow across each row.
- Title project task lists as `Repository (name) Tasks` while retaining the
  selected date. Display Total time as a small label above a large orange
  duration, matching the main report; carry its cyan and orange accents into
  table headings and durations, and highlight hovered or focused task rows.

## [0.9.0] - 2026-10-27 @ 18:03

This release is named for the element **Praseodymium (Pr)**. Praseodymium compounds 
can color glass yellow-green and are used in some strong permanent magnets.

### Summary

Refresh DevLog's pinned BMForge guidance to 0.14.0 and restore offline update
checks after the upstream manager moved. Make project task drill-downs easier
to scan with a dated title, readable total time and a compact task table.

### Changed

- Redesign the Tasks screen with a project/date title and a Total time subtitle,
  showing seconds only for totals under five minutes. List Task #, 24-hour Start
  Time, commit-message Description and Duration in a scrollable table; durations
  use whole hours and minutes, and task numbers link to their details.
- Update all 10 pinned BMForge skills, the project-local manager and lock
  fingerprints to BMForge 0.14.0 (`87ba468ffb83`); align project instructions
  with its implementation authorization and changelog guidance.

## [0.8.0] - 2026-10-26 @ 19:14

This release is named for the element **Caesium (Cs)** The precise frequency 
of a transition in caesium-133 defines the SI second.

### Summary

Correct completed task timing by dragging work boundaries on a timeline, with
live elapsed-time previews and an explicit Save or Cancel.

### Changed

- Replace completed tasks' pause-entry forms with proportional work blocks,
  pause and idle gaps, draggable start/stop boundaries, fixed neighbouring work,
  a fixed vertical Commit line and a page-load-time marker. Keep all work before
  the recorded commit/completion time. Add zoom, keyboard adjustments and
  read-only recorded intervals when JavaScript is unavailable.
- Save boundary corrections atomically, reject stale edits and overlapping
  work, preserve task/commit events and timestamp precision, and include corrected
  work in date-filtered task lists even outside its original lifecycle dates.

## [0.7.1] - 2026-10-26 @ 18:25

This release is named for the element **Xenon (Xe)**. Xenon is used in powerful 
lamps and some spacecraft ion thrusters.

### Summary

Make report sections collapsible and show each day's total above its chart bar.

### Changed

- Let Reporting, Current Task, Daily hours and Tasks collapse to their headings,
  with mouse or keyboard controls. Keep sections expanded on initial load.
- Label each daily bar with its hours, using a smaller version of the Total
  hours font and color. Fit labels to narrow screens and update them when
  projects are toggled in the legend.

## [0.7.0] - 2026-10-25 @ 19:16

This release is named for the element **Indium (In)**. Indium tin oxide forms 
transparent conductive coatings used in touchscreens and displays.

### Summary

Show active task time in `dl status` and the saved pause timestamp in `dl pause`.
Show the currently running task and rounded, readable active time on the report page.
Add pinned guidance for production evidence collection and local root-cause
analysis.

### Added

- Add a Current Task panel between Reporting and Daily hours, showing the global
  running task and repository or `No task currently running`. Display active time
  without pauses, rounded up to minutes for hours or seconds for shorter tasks.
- Add the optional `bmforge-rca` skill from BMForge revision `29f90eb16f11`,
  with its supporting references and lock fingerprint; update the project-local
  manager to recognize it. Collect production evidence through read-only SSH,
  then reproduce, debug and fix locally.

### Changed

- Format running-task status as `Repository (bmforge): Task #17 running for
  HH:MM hours`, showing total active time across resumes and excluding pauses.
- Format pause confirmations as `Repository (mycount): Task #12 paused on
  YYYY-MM-DD HH:MM:SS` in the configured timezone. Keep messages for already
  paused tasks and no task unchanged.

## [0.6.0] - 2026-10-25 @ 11:25

This release is named for the element **Palladium (Pd)**. Palladium can 
absorb remarkably large quantities of hydrogen relative to its own volume.

### Summary

Check the globally running task from any directory with `dl status`. Refresh
the pinned BMForge guidance for project maintenance and future UI work.

### Added

- Add `dl status`, a read-only ZMQ/database query that reports the active
  repository and task ID, or that no task is currently running.

### Changed

- Refresh all nine pinned BMForge skills and the project-local manager to
  upstream revision `fca87103c710`, including HTTP 0.4.0 design guidance and
  immediate changelog maintenance requirements; update lock fingerprints.

## [0.5.7] - 2026-10-25 @ 10:13

This release is named for the element **Ruthenium (Ru)**. Ruthenium belongs 
to the platinum group and can improve the hardness and wear resistance of 
electrical contacts.

### Added

- Show a **Last updated** timestamp in the footer of report and task pages,
  using the page render time in the configured local timezone.

### Changed

- Move the application subtitle into the header and tighten introduction and
  filter spacing.

## [0.5.6] - 2026-10-25 @ 09:42

This release is named for the element **Technetium (Tc)**. Technetium was the
first element produced artificially, and its isotope technetium-99m is widely
used in medical imaging.

### Changed

- Match BMDynIP's report-server styling across DevLog's report and task pages:
  a bordered full-width header, compact title, navigation and version display,
  wider bordered panels, and navy, cyan and orange colors.
- Match the daily-hours chart background to the page and keep mobile date
  filters wide enough to display complete dates.
- Give the main page separate Reporting, Daily hours and Tasks panels, with
  matching heading styles and the date/hour task links in their own frame.

## [0.5.5] - 2026-10-25 @ 09:12

This release is named for the element **Molybdenum (Mo)**. Molybdenum retains 
strength at high temperatures and is an important additive in tough steels.

### Changed

- Use darker shades of each project color for the daily-hours chart's 4 px bar
  borders and matching 2 px task dividers.

## [0.5.4] - 2026-10-25 @ 09:07

### Fixed

This release is named for the element **Niobium (Nb)**. Niobium helps create 
superconducting magnets used in MRI machines and particle accelerators.

- Make task dividers easier to see by brightening the shared bar-border and
  divider color and rendering the 2 px horizontal strokes without blurred edges.

## [0.5.3] - 2026-10-25 @ 08:51

This release is named for the element **Zirconium (Zr)**. Zirconium alloys are 
used to clad nuclear fuel because they absorb relatively few neutrons.

### Changed

- Restore the daily-hours chart's 2 px task separators to the brighter color
  used by each project bar's border.

## [0.5.1] - 2026-10-25 @ 08:46

This release is named for the element **Yttrium (Y)**. Yttrium compounds are 
used in phosphors and lasers, including the widely used YAG laser.

### Changed

- Use the site background color for the daily-hours chart's 2 px task separators
  to make divisions within each project bar easier to see.

## [0.5.0] - 2026-10-25 @ 08:40

This release is named after the element **Strontium (Sr)**. Strontium salts 
produce the brilliant red colors in many fireworks.

### Changed

- Add brighter 4 px borders around project bars in the daily-hours chart and
  2 px horizontal separators showing individual task sizes within each project.
  Separators stay aligned when filtering or toggling projects in the legend.

## [0.4.4] - 2026-10-25 @ 08:16

This release is named for the element **Rubidium (Rb)**. Rubidium is so reactive 
that it is normally stored away from air and moisture.

### Fixed

- Clear the repository filter when returning from task lists or task details
  with **Back to report**, preserving the selected date range and language.

## [0.4.3] - 2026-10-25 @ 08:05

This release is named for the element **Krypton (Kr)**. Krypton is a noble 
gas whose name comes from a Greek word meaning “hidden.”

### Changed

- Show elapsed time for pauses in task timelines, using the same `HH:MM:SS`
  format as active intervals.

## [0.4.2] - 2026-10-25 @ 06:53

This release is named for the element **Bromine (Br)**. Bromine is one of only two 
elements that are liquids near room temperature.

### Changed

- Uninstall removes all DevLog installation files, configuration, and logged
  data, including the server's database, database account, service and system
  account/group. Only the root-protected database credentials are retained.
- Server reinstall reuses retained credentials to recreate the database and
  account. Server installation now requires the MariaDB administrator client
  even when credentials already exist; upgrades continue preserving data.

## [0.4.1] - 2026-10-25 @ 06:22

This release is named for the element **Selenium (Se)**. Selenium is essential in 
tiny amounts for human health but can be toxic in excess.

### Changed

- Format task timestamps as `yyyy-mm-dd hh:mm:ss` in the configured local
  timezone, show elapsed `HH:MM:SS` for each active interval, and use
  `yyyy-mm-dd hh:mm` examples for pause edits.

## [0.4.0] - 2026-10-25 @ 05:58

The **Arsenic** release is named after the element **Arsenic (As)**. Arsenic has 
a long history as a poison, but some arsenic compounds are also used as medicines.

### Added

- Extend the BMForge project bootstrap with release metadata, release tooling,
  CMDB checks and disabled install/upgrade/uninstall stubs.
- Add `setup-branches` with a read-only `--dry-run` preview to create local
  `dev` and initial feature branches after a reviewed scaffold commit, refusing
  to overwrite existing branches.

### Changed

- Re-pin project-owned BMForge skills to snapshot `7047662` (PR #3), including
  updated installation lifecycle, ZeroMQ Unicode validation and release-template
  guidance.
- Make BMForge update checks read-only and offline against a clean local `main`
  checkout, configurable through `BMFORGE_SOURCE` or `--source`. Report the cached
  revision or an unavailable check without fetching, cloning or applying updates.

## [0.3.4] - 2026-10-25 @ 05:05

This release is named for the element **Gallium (Ga)**. Gallium can melt in the warmth of your hand because its melting point is about 30°C.

### Added

- Drill down from report dates and project bars to tasks, commit details and
  active/pause timelines.
- Insert a retrospective pause into a closed active interval to remove forgotten
  overnight time. Daily/project totals recalculate while task completion and Git
  metadata are preserved. The editor supports timezone offsets, inline validation
  and stale-edit rejection.

## [0.3.2] - 2026-10-24 @ 21:55

This release is named for the element **Nickel (Ni)**. Nickel is used in many coins and is also a key ingredient in numerous stainless-steel alloys.

### Changed

- Reorder the 20 project colors to increase contrast between neighboring stacks.

## [0.3.1] - 2026-10-24 @ 21:50

### Changed

The **Cobolt (Co)** release is named after the element. Cobalt compounds have produced vivid blue glass and ceramics for thousands of years.

- Use the supplied 20-color palette for project bars and omit `nadimghaznavi/`
  from project legend labels.

## [0.3.0] - 2026-10-24 @ 21:43

This release is named for the element **Iron (Fe)**. Earth's core is made mainly of iron, and flowing liquid metal in the outer core helps generate our magnetic field.

### Changed

- Stack each day's tracked hours by project using distinct colors, with the
  project legend below the Date label and project hours in segment tooltips.

## [0.2.1] - 2026-10-24 @ 19:43

This release is named for the element **Chromium**. Chromium helps stainless 
steel resist rust by forming a thin protective oxide layer.

### Changed

- Apply a dark green theme to the daily-hours report, including form controls,
  the hours table, and the chart with matching labels, gridlines, and tooltips.

## [0.2.0] - 2026-10-24 @ 19:26

This should be considered the initial release. The initial rollout was butchered using Git.

### Fixed

- Reject escaped lone Unicode surrogates in incoming ZeroMQ JSON envelopes before activity dispatch. A malformed request receives `invalid_request` without terminating the socket worker; valid Unicode and subsequent requests still work.
- Make fresh server installation preflight (including `--check`) require the `mariadb` executable when database provisioning will use it. Client-only installs and non-provisioning upgrades do not acquire that dependency.
- Close the BMForge 0.9.0 installation lifecycle gaps: implement role-aware
  `uninstall.sh` and read-only `--check` support for install, install-server,
  upgrade and uninstall without changing the client/server dependency split.
- Publish an installation ownership manifest, readable CMDB constants, and
  a last-successful-version marker for both client and server deployments.
  Preserve configuration and database data during uninstall.
- Install a project-specific release script from the BMForge template, keeping
  `pyproject.toml` version synchronized with `DDevLog.VERSION` during releases.
- Validate source package and literal CMDB versions before host changes.

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
