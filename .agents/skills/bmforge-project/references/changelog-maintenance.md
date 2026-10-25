---
title: Changelog Maintenance
lang: en
locale: en-US
language_name: English
translation_key: bmforge-changelog-maintenance
---

**Update `CHANGELOG.md` for every completed logical change, as part of the same task.** A change is not finished until the changelog describes it. Do not save changelog writing for a release, the end of a session, or a later documentation pass.

## Where This Fits

| Stage | Responsibility | Process |
| --- | --- | --- |
| Project setup | Create the changelog and its single `Unreleased` heading | [Release Setup]({{ site.baseurl }}{% link pages/release-setup.md %}) |
| Every development or maintenance change | Update `Unreleased` and its summary immediately | This process |
| Release | Assign version and timestamp to accumulated entries | [Creating a Release]({{ site.baseurl }}{% link pages/creating-a-release.md %}) |

## Every Change Must Be Recorded

1. When a logical change is complete, **update `CHANGELOG.md` in that same work item**. This applies to features, bug fixes, refactoring, tests, documentation, dependencies, configuration, installation, deployment, and operational maintenance, even when the change is small.
2. Record its result under the existing `## [Unreleased]` heading. There must be exactly one `Unreleased` heading. Make the entry before you consider the task complete or commit it with the related work.
3. Describe what changed and why it matters to users, operators, developers, or project maintenance. Use `### Added`, `### Changed`, `### Fixed`, or `### Removed` when appropriate; do not create empty headings.
4. Group the file edits belonging to one logical change into a concise entry, but do not omit a separate change simply because it is small. Record the actual outcome, not speculation or unfinished attempts.
5. Before handing off work, verify that the changelog matches the implementation and that previous unreleased entries and published release history are intact.

A changelog records completed changes, not a file-by-file transcript. Intermediate edits that are subsequently undone do not need entries; a finished change to tests, documentation, or configuration does.

## Make `### Summary` the Default

**Do not reserve `### Summary` for large releases.** Add or refresh it as soon as a meaningful feature, fix, workflow, reliability, or maintenance improvement is completed, even if that is the only change since the last release. For a collection of changes, keep its one- or two-sentence description current as each new outcome is recorded. A trivial typo-only edit can use a bullet without a summary when a summary would add no information.

Place one `### Summary` directly below `## [Unreleased]`, before categorized entries. **Do not create multiple `### Summary` headings in the same unreleased or versioned section.** Future releases may each contain their own summary. Describe the benefit or problem solved instead of repeating bullet headings.

```markdown
## [Unreleased]

### Summary

The event log now refreshes without losing the user's place, making live monitoring easier to follow.

### Fixed

- Preserve the selected event and scroll position during refresh.
```

When subsequent work is completed, update the existing summary if the overall description has changed and add the appropriate changelog entry. This produces frequent, useful summaries without duplicate headings.

## Hand Off to the Release Script

Leave released sections unchanged and record new work under `Unreleased`. During normal development, leave version numbers, timestamps, and codenames to the release process.

The release script inserts a versioned, timestamped heading immediately below `## [Unreleased]`. The accumulated entries, including `### Summary` when present, become part of that release. The new `Unreleased` section is then ready for further changes. Follow [Creating a Release]({{ site.baseurl }}{% link pages/creating-a-release.md %}) when the owner chooses to publish.

**Completion check:** Every completed logical change is represented, `### Summary` describes meaningful changes, only one summary exists per section, and release history is preserved.

---

[Back]({{ site.baseurl }}{% link index.md %})
