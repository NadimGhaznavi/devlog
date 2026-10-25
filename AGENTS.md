# Project engineering instructions

This project uses **pinned BMForge Codex skills**. These are project-owned copies,
not live imports from BMForge or another application.

Before the first BMForge-related edit in a Codex session, run the **read-only**,
**offline** update check from the repository root:

    python3 .agents/bmforge/manage.py check --project .

The check reads a clean local BMForge main checkout at
~/.cache/bmforge-upstream (override with BMFORGE_SOURCE or --source).
It never fetches or clones. Refresh that checkout separately with
'git pull --ff-only', outside this check. "CURRENT" means current as of the
reported cached source revision, not necessarily the newest GitHub commit.
Report available changes or an unavailable check to the user. **Do not apply
updates**, reinstall skills, or replace approved technologies without explicit
user authorization. Continue using the pinned skills unless instructed otherwise.

Read `.agents/skills/bmforge-project/SKILL.md` for architecture. Every new app
also follows the pinned `bmforge-constants`, `bmforge-localization` and
`bmforge-installation` skills: centralize programmatic identifiers, prepare
English localization keys from its first user-facing feature, and implement
the installation lifecycle for the actual application before the first release.
Add translations only when requested, never by guessing. Invoke other
components as needed.
Follow each selected skill's local
`references/specification.md` and approved module inventory. Never invent another
framework, database driver or plotting library as a shortcut.

Component selection and application-specific behaviour belong to this project's
requirements. A pinned skill is an instruction bundle, not executable app code.

Bootstrap provided `scripts/new-release.sh` with metadata, changelog and
deployment-disabled install/upgrade/uninstall stubs. Complete and test these
stubs through `bmforge-installation` once the application topology is known.
Every successful installation must create the application-owned BASE_DIR and
last-successful `.deployment-version`, even for a client or custom library.
Do not run release or deployment tools, commit, tag or push without explicit
user authorization. Once the user reviews and commits the scaffold on local
main, use `python3 .agents/bmforge/manage.py setup-branches --project . --dry-run`
to preview, then `setup-branches` with user approval to create local dev and
feat/maint-0.1.0. It never commits or pushes. Never re-create existing refs.
Read the pinned project's release-setup and creating-a-release references
before release work.
