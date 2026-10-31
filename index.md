---
title: Project Time Tracker
author_profile: true
layout: single
---

**DevLog** tracks time spent working in GitHub repositories.

- Start, pause and complete tasks from the command line.
- Review daily hours, project history and releases in the web interface.
- Track one active task at a time, with paused time excluded.

---

## User Guides

- [Installation](#installation)
- [Tracking work](#tracking-work)
- [Reports](#reports)
- [Changelog](CHANGELOG.md)

### Installation

Requires Python 3.11+ and Git. The server also needs Linux/systemd and local
MariaDB with administrator socket access. Run from a release checkout:

```bash
sudo ./scripts/install.sh -server SERVER_HOST  # client machine
sudo ./scripts/install-server.sh              # server machine
sudo ./scripts/upgrade.sh                     # upgrade either role
```

Add `/opt/prod/devlog/bin` to your PATH. Configuration is in
`/opt/prod/devlog/conf/devlog.json`; the client connects on port **19701**.
Use `--check` for prerequisite checks or `sudo ./scripts/uninstall.sh` to remove
the installation. Server uninstall deletes tracked data; saved database
credentials are retained.

### Tracking work

Run these commands inside a GitHub repository checkout:

```bash
dl status                    # show the active task; works from any directory
dl start                     # start or resume this repository's task
dl pause                     # pause it
dl commit "Describe changes" # commit, complete the task and push
dl publish                   # run this repository's release script
dl releases sync             # record existing local release tags
```

Switching repositories with `dl start` pauses the previous task. Start a new
task after committing. If recording a successful commit fails, recover with
`dl commit --record FULL_COMMIT_SHA`. Resolve push failures with ordinary Git.

### Reports

Open `http://SERVER_HOST:19700/` on your trusted network.

- **Daily hours:** filter by dates and repository. Colors and patterns match
  the legend and Daily table swatches. Click a bar total for that day's report.
- **Daily:** view one day's tasks across projects.
- **Tasks:** review tasks and releases for the selected period.
- **Projects:** view one project's complete history.

Open a completed task to correct its work intervals by dragging or resizing
them, or entering precise start and end times. Editing uses browser-local time.
Releases appear alongside tasks and do not add tracked time.

