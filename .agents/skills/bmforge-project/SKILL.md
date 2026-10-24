---
name: bmforge-project
description: Apply BMForge's pinned greenfield application architecture, Activity/Interface/Entity classification, engineering contract and technology boundaries. Use for new application design, module placement, component selection and Codex implementation planning.
---

# Build within the BMForge contract

Read `references/engineering-contract.md`, `references/classification.md`, `references/component-blueprints.md` and `references/specification-lifecycle.md` only as needed. This skill controls application architecture, not an application implementation.

- Start from explicit user requirements. DevLog-sized applications are only useful examples; do not automatically build a time tracker or preselect components.
- Every new app adopts `bmforge-constants` for stable domain-grouped identifiers and `bmforge-localization` for source-language message keys, even when only English is initially populated. Do not localize API identifiers or generate unrequested translations.
- Separate `activity/` (use-case orchestration), `interface/` (technology and domain bridges), and `entity/` (data), with `constants/` and `server/` only where appropriate. Use composition; avoid invented frameworks, base classes and unused packages.
- Select locally installed component skills by requirement. If a missing component is needed, ask before using `python3 .agents/bmforge/manage.py add --project . --components <name>`; do not silently install one.
- Infrastructure modules and browser libraries are fixed by the selected skill's local `references/specification.md`. Ask before deviating, introducing alternatives or adding unrelated frameworks.
- Each application owns its copied/adapted implementation and tests. Do not import BMForge or another application's runtime code.
- Run `python3 .agents/bmforge/manage.py check --project .` before the first BMForge-derived edit in a Codex session; notify the user about available versions. Checking does not authorise applying them.
- Derive the smallest coherent plan, test acceptance criteria, and keep user-controlled release operations outside this skill.
