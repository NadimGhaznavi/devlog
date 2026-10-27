---
name: bmforge-project
description: Apply BMForge's pinned greenfield application architecture, Activity/Interface/Entity classification, engineering contract and technology boundaries. Use for new application design, module placement, component selection and Codex implementation planning.
---

# Build within the BMForge contract

Read `references/engineering-contract.md`, `references/classification.md`, `references/component-blueprints.md` and `references/specification-lifecycle.md` only as needed. This skill controls application architecture, not an application implementation.

- **Implementation authorization gate:** Discussion, read-only investigation and design are not permission to change a project. Do not edit files or install packages until the user clearly authorizes the agreed implementation. A direct implement/fix request counts without magic words. After approval, complete the scoped work and tests without per-file prompts; pause for material scope changes, new dependencies or unapproved architecture. Commit, push, release and deploy remain separately authorized.
- Start from explicit user requirements. DevLog-sized applications are only useful examples; do not automatically build a time tracker or preselect components.
- Every new app adopts `bmforge-constants` for stable identifiers, `bmforge-localization` for source-language message keys, and `bmforge-installation` for all three install/upgrade/uninstall operations. Even a library-only or client-only installation must leave a versioned, owned `BASE_DIR`. Do not claim an installed version for an unverified package. Do not localize API identifiers or generate unrequested translations.
- Separate `activity/` (use-case orchestration), `interface/` (technology and domain bridges), and `entity/` (data), with `constants/` and `server/` only where appropriate. Use composition; avoid invented frameworks, base classes and unused packages.
- Select locally installed component skills by requirement. If a missing component is needed, ask before using `python3 .agents/bmforge/manage.py add --project . --components <name>`; do not silently install one.
- Infrastructure modules and browser libraries are fixed by the selected skill's local `references/specification.md`. Ask before deviating, introducing alternatives or adding unrelated frameworks.
- Each application owns its copied/adapted implementation and tests. Do not import BMForge or another application's runtime code.
- **Every completed logical change requires an immediate `CHANGELOG.md` update under `## [Unreleased]`**, including code, tests, documentation, configuration and small fixes. For every meaningful improvement, add or refresh one plain-English `### Summary`, even for a single change. Do not defer either step to release time. Read `references/changelog-maintenance.md` and verify the entry before declaring the task complete.
- Run `python3 .agents/bmforge/manage.py check --project .` before the first BMForge-derived edit in a Codex session; notify the user about available versions. Checking does not authorise applying them.
- Bootstrap already generated `scripts/new-release.sh`, version metadata, changelog, CMDB checker and disabled lifecycle scripts. After an explicitly approved first commit on `main`, the project-local `manage.py setup-branches --dry-run` and `setup-branches` actions establish the local `dev`/feature release lineage. Do not silently commit or push. Once the application's actual topology is known, follow `bmforge-installation` to complete and test all three lifecycle operations before declaring the app release-ready. Refer to `references/release-setup.md` and `references/creating-a-release.md` when the user asks to release; never create an alternative release system or run it without authorisation.
- Derive the smallest coherent plan, test acceptance criteria, and keep user-controlled release operations outside this skill.
