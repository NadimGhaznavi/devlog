---
title: "Tracking work"
lang: en
locale: en-US
language_name: English
translation_key: devlog-tracking-work
---

Run these commands inside a GitHub repository checkout. DevLog identifies the
project from its `origin` remote.

```bash
dl status                    # show the active task; works from any directory
dl start                     # start or resume this repository's task
dl pause                     # pause it
dl commit "Describe changes" # commit, complete the task and push
```

Only one task runs at a time. Switching repositories with `dl start` pauses the
previous task. Returning to a paused repository resumes its unfinished task;
paused time is excluded from reports. After committing, `dl start` creates a new
task for that repository.

## Commit and recovery

`dl commit` stages the repository's changes, creates a commit, records the
completed task and pushes. If recording a successful commit fails, recover with
the full commit SHA:

```bash
dl commit --record FULL_COMMIT_SHA
```

This records the existing commit without committing or pushing again. Resolve
push failures with ordinary Git.

## Releases

```bash
dl publish                   # run this repository's release script
dl releases sync             # record existing local release tags
dl releases sync --dry-run   # inspect local tags without contacting the server
```

`dl publish` runs the repository's existing release script. After a successful
release, it records newly discovered version tags in DevLog. If recording fails,
use `dl releases sync` to recover without publishing again.

Release synchronization reads local Git tags; it does not fetch from the remote.
Releases appear alongside tasks in reports and do not add tracked time.

---

[Documentation index]({{ site.baseurl }}{% link index.md %})
