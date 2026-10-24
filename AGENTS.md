# Project engineering instructions

This project uses **pinned BMForge Codex skills**. These are project-owned copies,
not live imports from BMForge or another application.

Before the first BMForge-related edit in a Codex session, run the **read-only**
update check from the repository root:

    python3 .agents/bmforge/manage.py check --project .

Report available changes or an unavailable check to the user. **Do not apply
updates**, reinstall skills, or replace approved technologies without explicit
user authorization. Continue using the pinned skills unless instructed otherwise.

Read `.agents/skills/bmforge-project/SKILL.md` for architecture. Every new app
also follows the pinned `bmforge-constants` and `bmforge-localization` skills:
centralize stable programmatic identifiers and prepare English localization keys
from its first user-facing feature. Add real translations only when provided or
requested, never by guessing. Invoke other component skills as needed.
Follow each selected skill's local
`references/specification.md` and approved module inventory. Never invent another
framework, database driver or plotting library as a shortcut.

Component selection and application-specific behaviour belong to this project's
requirements. A pinned skill is an instruction bundle, not executable app code.
