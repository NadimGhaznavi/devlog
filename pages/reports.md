---
title: "Reports"
layout: single
classes: wide
author_profile: true
lang: en
locale: en-US
language_name: English
translation_key: devlog-reports
---

Open `http://SERVER_HOST:19700/` on your trusted network, replacing `SERVER_HOST`
with your DevLog server's hostname or IP address.

## Review your work

- **Daily hours:** filter by dates and repository. Project colors and patterns
  match the legend and Daily table swatches. Click a bar total for that day's
  report, or a project segment to see that project's tasks for the day.
- **Daily:** view one day's tasks across projects and filter by project.
- **Tasks:** review tasks and releases for the selected period.
- **Projects:** view one project's complete history across all dates.

Reports split active work at day boundaries in the server's configured timezone.
Paused time is excluded. Releases appear alongside tasks, with distinct amber
rows, and do not contribute to hours.

## Correct a completed task

Open a completed task to review its recorded intervals. Select a work interval
and drag it to move it, or resize either edge. You can also enter precise start
and end times and choose **Save timing**; **Cancel** discards unsaved form edits.

The timeline and precise editor use your browser's local timezone.
Recorded interval details use the report timezone. Full timestamps
use `yyyy-mm-dd hh:mm:ss`. During a repeated daylight-saving hour, specify the
UTC offset when entering a new time; nonexistent local times are rejected.

Corrections must stay before the task's completion time and cannot overlap
other recorded work. Successful saves refresh the recorded intervals and total
duration. If a save has an uncertain outcome, the editor reads the server's
current values before allowing another edit. Follow a reload message if it
cannot recover.

Recorded intervals remain readable when JavaScript or the timeline library is
unavailable.

---

[Documentation index]({{ site.baseurl }}{% link index.md %})
