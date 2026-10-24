---
title: Creating a Release
lang: en
locale: en-US
language_name: English
translation_key: bmforge-creating-a-release
---

Publish a completed feature branch using the tooling from [Release Setup]({{ site.baseurl }}{% link pages/release-setup.md %}). The project owner chooses the release version and message.

## Prepare the Release

Finish the relevant verification and documentation, review the entries accumulated through [Changelog Maintenance]({{ site.baseurl }}{% link pages/changelog-maintenance.md %}), and commit all work. Run from a feature branch with a clean working tree. Incorporate any changes from `main` into `dev`, then from `dev` into the feature branch, before releasing.

If deployment tracking is enabled, regenerate and commit a changed dependency map before releasing. See [Deployment Impact Tracking]({{ site.baseurl }}{% link pages/deployment-impact-tracking.md %}).

## Run the Script

From an interactive terminal:

```sh
scripts/new-release.sh 0.1.0 "Pioneer"
```

Supply the semantic version without a leading `v`. Prereleases and build metadata are supported. The message becomes `CMDB_CODENAME`, so use a nonempty message of at most 255 characters without control characters.

The optional third argument selects the next feature branch. Otherwise the script increments the released patch number, for example `0.1.0` produces `feat/maint-0.1.1`.

```sh
scripts/new-release.sh 0.1.0 "Pioneer" feat/next-feature
```

Review the source branch, tag, codename, next branch, and remote in the summary. Answer `y` to create and push the release. Cancellation leaves the working branch and release files unchanged; the preflight fetch may have refreshed remote-tracking refs and tags.

## What the Script Publishes

After local and remote checks and confirmation, the script:

1. Merges the feature branch into `dev` with a merge commit.
2. Updates `VERSION`, `CMDB_CODENAME`, and the changelog's release version and local timestamp. When enabled, it also records deployment impact.
3. Commits the release metadata and merges `dev` into `main`.
4. Creates an annotated `v<version>` tag and advances `dev` to `main`.
5. Atomically pushes `main`, `dev`, and the tag to `origin`.
6. Creates the next local feature branch. It does not push that branch.

This publishes Git refs. Application installation or upgrades use the project's deployment scripts. A push to `main` may also trigger the configured documentation publishing workflow.

## Verify or Recover

After success, confirm the released constants, changelog, annotated tag, matching `main` and `dev` tips, remote refs, and clean next feature branch. Verify CMDB discovery after deployment using [CMDB Compliance]({{ site.baseurl }}{% link pages/cmdb-compliance.md %}).

On failure, the script stops and reports its active step. Inspect `git status`, branch history, tags, remote refs, and changed release files before deciding how to recover. Local merges, commits, and tags are not rolled back automatically. An atomic push updates all requested remote refs together or none; a rejected push can still leave local release commits and the tag in place. A failure creating the next branch may occur after the release was already published. Do not blindly rerun the release command.

---

[Back]({{ site.baseurl }}{% link index.md %})
