---
title: Git Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.git"
spec_version: "0.1.0"
spec_status: "draft"
translation_key: bmforge-component-git
---

# Git

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

This is a small, **application-owned** interface for two Git operations: **Publish** and **Commit**. Copy the [local template]({{ '/components/templates/git/Git.py' | relative_url }}) into the consuming application's own package; do not import BMForge or another application at runtime. Follow the [engineering contract]({{ site.baseurl }}{% link pages/engineering-contract.md %}) and [component traceability]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}).

## Approved runtime modules

This is the complete approved module inventory for this component. It runs on Linux/POSIX and invokes the installed **Git command-line executable**; Git is an external executable, not a Python package.

| Origin | Module | Purpose |
| --- | --- | --- |
| Python stdlib | `contextlib` | Context manager for the exclusive publishing session |
| Python stdlib / POSIX | `fcntl` | Nonblocking advisory lock on the dedicated publishing checkout |
| Python stdlib | `os` | Pass environment with `GIT_TERMINAL_PROMPT=0` |
| Python stdlib | `pathlib` | Checkout and managed-file paths |
| Python stdlib | `subprocess` | Run the installed Git CLI without invoking a shell |
| Python stdlib | `tempfile` | Atomic writes of generated publication files |

**No GitPython, Dulwich, ORM, task queue, or GitHub API library.** Codex may configure paths, branch, managed-file names, and commit messages. If these modules or this CLI-based approach cannot satisfy the requirement, **stop and request the user's approval** before replacing or adding technology. Application activity code is separate from this infrastructure contract.

## Local source and provenance

- **Ready-to-copy template:** `components/templates/git/Git.py`. It is independent of Snake Web and implements both operations.
- **Frozen source reference:** `components/reference/snake-web-code/snakewebcode/interface/GitPublisher.py`, copied from `NadimGhaznavi/snake-web-code` commit `b4a6837169950cd3940ba53231298ce6033b75a5` (24 October 2026).
- **Verification:** `tests/test_git_component.py` exercises the template against temporary repositories and local bare remotes, without touching real application repositories.

The original `GitPublisher` uses Snake Web-specific report paths, messages, and constants. Those are **not** generic Git requirements. Do not copy them into another project. Define that application's own managed paths and generated content.

## Operation 1: Commit

`Git(checkout).commit(message)` runs these exact commands in the selected **repository root**:

```sh
git add . -v
git commit -m "<message>"
git push
```

`Git` executes them as argument arrays with `git -C <checkout>`, never through a shell. `push` uses the current branch's configured upstream; the caller must configure a remote, Git identity, and push credentials before running. All repository-root changes, including untracked files not ignored by Git, are staged.

The operation returns the verbose add and commit output after a successful push. Empty messages, a repository-root mismatch, an empty commit, failed Git commands, or a rejected push fail visibly. **A failed push may leave the commit locally.** Do not add automatic pulls, merges, retries, force-pushes, clean-ups, or branch switching to this operation. The caller resolves any conflict.

## Operation 2: Publish

`Git(checkout, branch="main", managed_paths=paths).publish(files, message)` publishes a map of `{relative_path: str_or_bytes}` to a **dedicated publishing clone**, not the developer's worktree. Use a caller-provided explicit list of managed paths.

1. Acquire an exclusive, nonblocking lock in the checkout's Git directory. Require the configured branch, a clean worktree, and repository-root checkout.
2. Fetch `origin` and fast-forward to upstream commits. Refuse divergent history or unrelated unpublished commits.
3. Write only approved managed files whose contents changed. Reject unapproved paths and symlink targets; stage and commit **only changed managed paths**. No change means no new commit.
4. Push to `origin` on the configured branch. Retry an earlier failed push **only when** the local unpublished commits affect managed files; do not force-push or silently discard local commits.
5. Return `True` if a push succeeded, `False` if nothing needed publishing; a failure raises an error and does not claim success.

The application prepares report data, selects output paths, and supplies the commit message. Git does **not** render HTML, query MariaDB, schedule jobs, create repositories, configure credentials, or perform release merges or tags. Those are separate responsibilities.

## Lifecycle and health

Git is a callable interface, **not a running server**. It has no listener or `/health` endpoint. The result of `commit` or `publish` tells the calling application whether the operation succeeded. An application's own health check may include Git-related capability only if that is an explicit application requirement.

## Acceptance checks

1. Commit stages modified and untracked files with `git add . -v`, creates the requested message, and pushes to the configured upstream.
2. Empty commit and rejected push fail visibly; a successful local commit is not discarded when its push fails.
3. Publish changes only approved managed files; unchanged content produces no duplicate commit.
4. Publish refuses dirty or wrong-branch checkouts and concurrent publishing.
5. After a rejected publish push, the next attempt pushes the existing managed commit without duplicating it.
6. All checks use disposable, local repositories and bare remotes; no network credentials or public repositories are needed.
7. Verify the generated application owns its Git template, declares the literal `BMFORGE_COMPONENT` metadata, and imports none of BMForge or Snake Web at runtime.

---

[Component Blueprints]({{ site.baseurl }}{% link pages/component-blueprints.md %}) · [Back to BMForge]({{ site.baseurl }}{% link index.md %})
