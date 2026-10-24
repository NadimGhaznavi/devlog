---
name: bmforge-git
description: Add BMForge's approved Python Git interface with exactly two operations, repository-wide add/commit/push and safe managed-file publication. Use when an application needs Git commits or published generated files.
---

# Git component

Read `references/specification.md` and `references/engineering-contract.md` first. Copy `assets/Git.py` into the consuming application's own interface package and adapt only application configuration.

- **Commit:** use exactly `git add . -v`, `git commit -m <message>`, `git push` from the specified repository root. It stages all changes. Do not add automatic fetches, merges, rebases, force-pushes or retry policies.
- **Publish:** use a dedicated, clean publishing clone and an explicit managed-file allowlist. Preserve the template's locking, safe fast-forward checks, managed-only commits and retry of a previously failed push.
- See `references/source/snake-web-code/snakewebcode/interface/GitPublisher.py` for the pinned source, but do not import Snake Web or transplant its report filenames.
- Do not automatically run release operations or commit user changes merely because the skill is installed. A user or explicit application requirement authorises such actions.
- Keep the literal `BMFORGE_COMPONENT` marker `bmforge.git` spec `0.1.0` and test real Git workflows against disposable local remotes.
